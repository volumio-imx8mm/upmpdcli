/* Copyright (C) 2016 J.F.Dockes
 *   This program is free software; you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation; either version 2 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 *
 *   You should have received a copy of the GNU General Public License
 *   along with this program; if not, write to the
 *   Free Software Foundation, Inc.,
 *   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
 */

#include "mediaserver.hxx"

#include "conman.hxx"
#include "contentdirectory.hxx"

using namespace std;

MediaServer::MediaServer(const string& deviceid, const string& friendlyname,
    const std::unordered_map<std::string, VDirContent>& files)
    : UpnpDevice(deviceid, files), m_UDN(deviceid), m_fname(friendlyname)
{
    m_cd = new ContentDirectory(this);
    m_cm = new UpMpdConMan(this);
}


MediaServer::~MediaServer()
{
    delete m_cd;
    delete m_cm;
}
