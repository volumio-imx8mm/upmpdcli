# Copyright (C) 2023 Giovanni Fulco
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# this should contain all methods which interact directly with the subsonic server

from subsonic_connector.connector import Connector
from subsonic_connector.list_type import ListType
from subsonic_connector.response import Response
from subsonic_connector.album_list import AlbumList
from subsonic_connector.album import Album
from subsonic_connector.artist import Artist
from subsonic_connector.song import Song

from tag_type import TagType
from element_type import ElementType

from item_identifier import ItemIdentifier

import connector_provider
import cache_manager_provider
import caching

import album_util
import config
import connector_provider
import art_retriever

import cmdtalkplugin

import secrets

from typing import Callable

# Func name to method mapper
dispatcher = cmdtalkplugin.Dispatch()
# Pipe message handler
msgproc = cmdtalkplugin.Processor(dispatcher)

def get_random_art_by_genre(
        genre : str,
        max_items : int = 100) -> str:
    connector : Connector = connector_provider.get()
    response : Response[AlbumList] = connector.getAlbumList(
        ltype = ListType.BY_GENRE,
        genre = genre,
        size = max_items)
    if not response.isOk(): return None
    album : Album = secrets.choice(response.getObj().getAlbums())
    if album: return album.getId()
    return None

def get_album_tracks(album_id : str) -> album_util.AlbumTracks:
    result : list[Song] = []
    connector : Connector = connector_provider.get()
    albumResponse : Response[Album] = connector.getAlbum(album_id)
    if not albumResponse.isOk(): raise Exception(f"Album with id {album_id} not found")
    album : Album = albumResponse.getObj()
    albumArtURI : str = connector.buildCoverArtUrl(album.getId())
    song_list : list[Song] = album.getSongs()
    sort_song_list_result : album_util.SortSongListResult = album_util.sort_song_list(song_list)
    current_song : Song
    for current_song in sort_song_list_result.getSongList():
        result.append(current_song)
    albumArtURI : str = connector.buildCoverArtUrl(album.getId())
    return album_util.AlbumTracks(
        codec_set_by_path = sort_song_list_result.getCodecSetByPath(),
        album = album, 
        song_list = result, 
        art_uri = albumArtURI,
        multi_codec_album = sort_song_list_result.getMultiCodecAlbum())

def get_albums(query_type : str, size : int = config.items_per_page, offset : int = 0) -> list[Album]:
    connector : Connector = connector_provider.get()
    albumListResponse : Response[AlbumList]
    if TagType.NEWEST.getQueryType() == query_type:
        albumListResponse = connector.getNewestAlbumList(size = size, offset = offset)
    elif TagType.RANDOM.getQueryType() == query_type:
        albumListResponse = connector.getRandomAlbumList(size = size, offset = offset)
    elif TagType.RECENTLY_PLAYED.getQueryType() == query_type:
        albumListResponse = connector.getAlbumList(ltype = ListType.RECENT, size = size, offset = offset)
    elif TagType.MOST_PLAYED.getQueryType() == query_type:
        albumListResponse = connector.getAlbumList(ltype = ListType.FREQUENT, size = size, offset = offset)
    elif TagType.HIGHEST_RATED.getQueryType() == query_type:
        albumListResponse = connector.getAlbumList(ltype = ListType.HIGHEST, size = size, offset = offset)
    elif TagType.FAVOURITES.getQueryType() == query_type:
        albumListResponse = connector.getAlbumList(ltype = ListType.STARRED, size = size, offset = offset)
    if not albumListResponse.isOk(): raise Exception(f"Cannot execute query {query_type} for size {size} offset {offset}")
    return albumListResponse.getObj().getAlbums()

def load_all_artists_by_genre(genre : str) -> set[str]:
    artist_id_set : set[str] = set()
    album_list : list[Album] = None
    offset : int = 0
    while not album_list or len(album_list) == config.subsonic_max_return_size:
        album_list_response : Response[AlbumList] = connector_provider.get().getAlbumList(
            ltype = ListType.BY_GENRE, 
            genre = genre,
            offset = offset,
            size = config.subsonic_max_return_size)
        if not album_list_response.isOk(): return set()
        album_list : list[Album] = album_list_response.getObj().getAlbums()
        cached : bool = False
        album : Album
        for album in album_list:
            artist_id : str = album.getArtistId()
            if not artist_id in artist_id_set:
                artist_id_set.add(artist_id)
                if not cached:
                    cache_manager_provider.get().cache_element_value(
                        ElementType.GENRE_ARTIST_LIST, 
                        genre, 
                        album.getId())
                    cached = True
        offset += len(album_list)
    return artist_id_set

def get_artist_art(artist_id : str, initializer_callback : Callable[[], None]) -> str:
    cache_manager : caching.CacheManager = cache_manager_provider.get()
    art_cache_size : int = cache_manager.get_cache_size(ElementType.ARTIST)
    if art_cache_size == 0: initializer_callback()
    artist_art : str = cache_manager.get_cached_element(ElementType.ARTIST, artist_id)
    if not artist_art:
        # can be new
        if art_cache_size == 0: initializer_callback()
        msgproc.log(f"get_artist_art searching artist_art for artist_id {artist_id}")
        identifier : ItemIdentifier = ItemIdentifier(ElementType.ARTIST, artist_id)
        artist_art = art_retriever.artist_art_retriever(identifier)
        # store if found
        if artist_art: cache_manager.cache_element_value(ElementType.ARTIST, artist_id, artist_art)
    return artist_art

def get_album_list_by_artist_genre(
        artist : Artist, 
        genre_name : str) -> list[Album]:
    result : list[Album] = list()
    album_list : list[Album] = None
    offset : int = 0
    while not album_list or len(album_list) == config.subsonic_max_return_size:
        album_list_response : Response[AlbumList] = connector_provider.get().getAlbumList(
            ltype = ListType.BY_GENRE,
            offset = offset,
            size = config.subsonic_max_return_size,
            genre = genre_name)
        if not album_list_response.isOk(): raise Exception(f"Failed to load albums for genre {genre_name} offset {offset}")
        album_list : list[Album] = album_list_response.getObj().getAlbums()
        current_album : Album
        for current_album in album_list if album_list and len(album_list) > 0 else []:
            if artist.getName() in current_album.getArtist():
                result.append(current_album)
        offset += len(album_list)
    return result


