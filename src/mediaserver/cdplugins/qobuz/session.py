# defined to emulate the session object from the tidal module, which is
# defined in the tidalapi part (we want to keep the qobuz api/ dir as
# much alone as possible.
from __future__ import print_function

import sys
import json
from upmplgmodels import Artist, Album, Track, Playlist, SearchResult, \
     Category, Genre
from upmplgutils import *
from qobuz.api import raw

# General limit for fetching stuff, in places where we do it in one chunk.
# The high limit set by Qobuz depends a bit on the nature of the request, but
# 100 works everywhere (some requests could use a bigger value).
general_slice = 100

class Session(object):
    def __init__(self):
        self.api = None
        self.user = None

    def login(self, username, password, appid, cfvalue):
        # self.api will already exist if get_appid() was called first, which means that the
        # appid/secret were obtained through the spoofer, not the config. This happens when we are
        # working for OH Credentials. Else we create the API with our input params which come from
        # the configuration (and still may be empty in which case the spoofer will be used).
        if not self.api:
            self.api = raw.RawApi(appid, cfvalue)
        data = self.api.user_login(username = username, password = password)
        if data:
            self.user = User(self, self.api.user_id)
            return True
        else:
            return False

    def get_appid(self):
        if not self.api:
            self.api = raw.RawApi(None, None)
        return self.api.appid
    
    def get_appid_and_token(self):
        return (self.api.appid, self.api.user_auth_token)
    

    def get_media_url(self, trackid, format_id=5):
        # Format id: 5 for MP3 320, 6 for FLAC Lossless, 7 for FLAC
        # Hi-Res 24 bit =< 96kHz, 27 for FLAC Hi-Res 24 bit >96 kHz &
        # =< 192 kHz
        url = self.api.track_getFileUrl(intent="stream",
                                        track_id = trackid,
                                        format_id = format_id)
        uplog("get_media_url got: %s" % url)
        return url['url'] if url and 'url' in url else None


    def loopget(self, max, getter, getterka, parser):
        slice = 20
        offset = 0
        all = []
        while max == 0 or offset < max:
            getterka['limit'] = slice
            getterka['offset'] = offset
            jsdata = getter(**getterka)
            try:
                ndata = parser(jsdata)
                #uplog("loopget: %s" % json.dumps(ndata, indent=4))
            except Exception as err:
                uplog("loopget: exception while parsing: %s" % err)
                break
            all.extend(ndata)
            uplog("GOT %d more (slice %d)" % (len(ndata), slice))
            if len(ndata) < slice:
                break
            offset += slice
            
        return all
        

    def get_album_tracks(self, albid):
        data = self.api.album_get(album_id = albid)
        album = _parse_album(data)
        return [_parse_track(t, album) for t in data['tracks']['items']]


    def get_playlist_tracks(self, plid):
        return self.loopget(
            1000, self.api.playlist_get,
            {'playlist_id' : plid, 'extra' : 'tracks'},
            lambda jsdata : [_parse_track(t) for t in jsdata['tracks']['items']]
            )

    def get_artist_albums(self, artid):
        data = self.api.artist_get(artist_id=artid, extra='albums')
        if 'albums' in data:
            albums = [_parse_album(alb) for alb in data['albums']['items']]
            return [alb for alb in albums if alb.available]
        return []

    def get_artist_similar(self, artid):
        data = self.api.artist_getSimilarArtists(artist_id=artid)
        if 'artists' in data and 'items' in data['artists']:
            return [_parse_artist(art) for art in data['artists']['items']]
        return []

    def get_featured_albums(self, genre_id='None', type='new-releases'):
        #uplog("get_featured_albums, genre_id %s type %s " % (genre_id, type))
        if genre_id != 'None':
            data = self.api.album_getFeatured(type=type,
                                              genre_id=genre_id,
                                              limit=general_slice)
        else:
            data = self.api.album_getFeatured(type=type, limit=general_slice)
            
        try:
            albums = [_parse_album(alb) for alb in data['albums']['items']]
            if albums:
                return [alb for alb in albums if alb.available]
        except:
            pass
        return []

    def get_featured_playlists(self, genre_id='None'):
        if genre_id != 'None':
            data = self.api.playlist_getFeatured(type='editor-picks',
                                                 genre_id=genre_id,
                                                 limit=general_slice)
        else:
            data = self.api.playlist_getFeatured(type='editor-picks',
                                                 limit=general_slice)
        if data and 'playlists' in data:
            return [_parse_playlist(pl) for pl in data['playlists']['items']]
        return []

    # content_type: albums/artists/playlists.  type : The type of
    # recommandations to fetch: best-sellers, most-streamed,
    # new-releases, press-awards, editor-picks, most-featured
    # In practise, and despite the existence of the
    # catalog_getFeaturedTypes call which returns the above list, I
    # could not find a way to pass the type parameter to
    # catalog_getFeatured (setting type triggers an
    # error). album_getFeatured() and playlist_getFeatured() do accept type.
    def get_featured_items(self, content_type, type=''):
        #uplog("FEATURED TYPES: %s" % self.api.catalog_getFeaturedTypes())
        data = self.api.catalog_getFeatured(limit=general_slice)
        #uplog("Featured: %s" % json.dumps(data,indent=4)))
        if content_type == 'artists':
            if 'artists' in data:
                return [_parse_artist(i) for i in data['artists']['items']]
        elif content_type == 'playlists':
            if 'playlists' in data:
                return [_parse_playlist(pl) for pl in data['playlists']['items']]
        elif content_type == 'albums':
            if 'albums' in data:
                return [_parse_album(alb) for alb in data['albums']['items']]
        return []

    def get_genres(self, parent=None):
        data = self.api.genre_list(parent_id=parent)
        return [Genre(id=None, name='All Genres')] + \
               [_parse_genre(g) for g in data['genres']['items']]

    def _search1(self, query, tp):
        uplog("_search1: query [%s] tp [%s]" % (query, tp))

        limit = 200
        slice = 200
        if tp == 'artists':
            limit = 20
            slice = 20
        elif tp == 'albums' or tp == 'playlists':
            limit = 50
            slice = 50
        offset = 0
        all = []
        while offset < limit:
            uplog("_search1: call catalog_search, offset %d" % offset)
            data = self.api.catalog_search(query=query, type=tp,
                                           offset=offset, limit=slice)
            ncnt = 0
            ndata = []
            try:
                if tp == 'artists':
                    ncnt = len(data['artists']['items'])
                    ndata = [_parse_artist(i) for i in data['artists']['items']]
                elif tp == 'albums':
                    ncnt = len(data['albums']['items'])
                    ndata = [_parse_album(i) for i in data['albums']['items']]
                    ndata = [alb for alb in ndata if alb.available]
                elif tp == 'playlists':
                    #uplog("PLAYLISTS: %s" % json.dumps(data, indent=4))
                    ncnt = len(data['playlists']['items'])
                    ndata = [_parse_playlist(i) for i in \
                             data['playlists']['items']]
                elif tp == 'tracks':
                    ncnt = len(data['tracks']['items'])
                    ndata = [_parse_track(i) for i in data['tracks']['items']]
            except Exception as err:
                uplog("_search1: exception while parsing result: %s" % err)
                break
            all.extend(ndata)
            #uplog("Got %d more (slice %d)" % (ncnt, slice))
            if ncnt < slice:
                break
            offset += slice

        if tp == 'artists':
            return SearchResult(artists=all)
        elif tp == 'albums':
            return SearchResult(albums=all)
        elif tp == 'playlists':
            return SearchResult(playlists=all)
        elif tp == 'tracks':
            return SearchResult(tracks=all)

    def search(self, query, tp):
        if tp:
            return self._search1(query, tp)
        else:
            cplt = SearchResult()
            res = self._search1(query, 'artists')
            cplt.artists = res.artists
            res = self._search1(query, 'albums')
            cplt.albums = res.albums
            res = self._search1(query, 'tracks')
            cplt.tracks = res.tracks
            res = self._search1(query, 'playlists')
            cplt.playlists = res.playlists
            return cplt

def _parse_artist(data):
    #uplog("_parse_artist: data %s" % data)
    kwargs = {'id' : data['id'], 'name' : data['name']}
    if 'image' in data and data['image'] and 'large' in data['image']:
        kwargs['image'] = data['image']['large']
    return Artist(**kwargs)


def _parse_genre(data):
    return Genre(id=data['id'], name=data['name'])


def _parse_album(json_obj, artist=None, artists=None):
    #uplog("Qobuz:_parse_album:DATA:\n%s"%json.dumps(json_obj, indent=4))
    if artist is None and 'artist' in json_obj:
        artist = _parse_artist(json_obj['artist'])
    #if artists is None:
    #    artists = _parse_artists(json_obj['artists'])
    available = json_obj['streamable'] if 'streamable' in json_obj else False
    #if not available:
    #    uplog("Album not streamable: %s " % json_obj['title'])
    kwargs = {
        'id': json_obj['id'],
        'name': json_obj['title'],
        'num_tracks': json_obj.get('tracks_count'),
        'duration': json_obj.get('duration'),
        'artist': artist,
        'available': available,
        #'artists': artists,
    }
    if 'image' in json_obj and 'large' in json_obj['image']:
        kwargs['image'] = json_obj['image']['large']
    if 'maximum_bit_depth' in json_obj:
        kwargs['maxbitdepth'] = str(json_obj['maximum_bit_depth'])
    if 'maximum_sampling_rate' in json_obj:
        kwargs['maxsamprate'] = str(json_obj['maximum_sampling_rate'])
    if 'maximum_channel_count' in json_obj:
        kwargs['maxchannels'] = str(json_obj['maximum_channel_count'])

    if 'releaseDate' in json_obj:
        try:
            # Keep this as a string else we fail to json-reserialize it later
            kwargs['release_date'] = json_obj['releaseDate']
            #kwargs['release_date'] = datetime.datetime(*map(int, json_obj['releaseDate'].split('-')))
        except ValueError:
            pass
    return Album(**kwargs)


def _parse_playlist(data, artist=None, artists=None):
    #uplog("_parse_playlist: data %s" % data)
    kwargs = {
        'id': data['id'],
        'name': data['name'],
        'num_tracks': data.get('tracks_count'),
        'duration': data.get('duration'),
    }
    for suff in ('300', '150', ''):
        try:
            kwargs['image'] = data['images' + suff][0]
            break
        except:
            pass
    return Playlist(**kwargs)


def _parse_track(json_obj, albumarg = None):
    artist = Artist()
    if 'performer' in json_obj:
        artist = _parse_artist(json_obj['performer'])
    elif 'artist' in json_obj:
        artist = _parse_artist(json_obj['artist'])
    elif albumarg and albumarg.artist:
        artist = albumarg.artist

    album = None
    if 'album' in json_obj:
        album = _parse_album(json_obj['album'], artist)
    else:
        album = albumarg

    available = json_obj['streamable'] if 'streamable' in json_obj else false
    #if not available:
    #uplog("Track no not streamable: %s " % json_obj['title'])

    #artists = _parse_artists(json_obj['artists'])
    kwargs = {
        'id': json_obj['id'],
        'name': json_obj['title'],
        'duration': json_obj['duration'],
        'track_num': json_obj['track_number'],
        'disc_num': json_obj['media_number'],
        'artist': artist,
        'available': available
        #'artists': artists,
    }
    if album:
        kwargs['album'] = album

    return Track(**kwargs)


class Favorites(object):

    def __init__(self, session):
        self.session = session

    def artists(self):
        return self.session.loopget(
            0, self.session.api.favorite_getUserFavorites,
            {'user_id' : self.session.user.id, 'type' : 'artists'},
            lambda r : [_parse_artist(item) for item in r['artists']['items']]
            )

    def albums(self):
        result = self.session.loopget(
            0, self.session.api.favorite_getUserFavorites,
            {'user_id' : self.session.user.id, 'type' : 'albums'},
            lambda r : [_parse_album(item) for item in r['albums']['items']]
            )
        return [alb for alb in result if alb.available]

    def playlists(self):
        return self.session.loopget(
            0, self.session.api.playlist_getUserPlaylists,
            {'user_id' : self.session.user.id},
         lambda r : [_parse_playlist(item) for item in r['playlists']['items']]
            )

    def tracks(self):
        result = self.session.loopget(
            0, self.session.api.favorite_getUserFavorites,
            {'user_id' : self.session.user.id, 'type' : 'tracks'},
            lambda r : [_parse_track(item) for item in r['tracks']['items']]
            )
        return [trk for trk in result if trk.available]


class User(object):
    def __init__(self, session, id):
        self.session = session
        self.id = id
        self.favorites = Favorites(self.session)

    def playlists(self):
        return self.session.get_user_playlists(self.id)
