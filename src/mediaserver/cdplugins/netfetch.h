/* Copyright (C) 2017-2018 J.F.Dockes
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

#ifndef _MEDIAFETCH_H_INCLUDED_
#define _MEDIAFETCH_H_INCLUDED_

#include "bufxchange.h"
#include "abuffer.h"

//
// Wrapper for a network fetch
//
// The transfer is aborted when the object is deleted, with proper
// cleanup.
//
// The end of transfer is marked by pushing an empty buffer on the queue
//
// All methods are supposedly thread-safe
class NetFetch {
public:
    NetFetch() {}
    virtual ~NetFetch() {}

    virtual void setTimeout(int secs) = 0;
    
    /// Start the transfer to the output queue.
    virtual bool start(BufXChange<ABuffer*> *queue, uint64_t offset = 0) = 0;

    // Wait for headers. This allows, e.g. doing stuff depending on
    // content-type before proceeding with the actual data
    // transfer. May not work exactly the same depending on the
    // underlaying implementation.
    virtual bool waitForHeaders(int maxSecs = 0) = 0;
    // Retrieve header value (after a successful waitForHeaders).
    virtual bool headerValue(const std::string& nm, std::string& val) = 0;

    // Check if the fetch is done and retrieve the results if it
    // is. This does not wait, it returns false if the transfer is
    // still running.
    // The pointers can be set to zero if no value should be retrieved
    enum FetchStatus {FETCH_OK=0, FETCH_RETRYABLE, FETCH_FATAL};
    virtual bool fetchDone(FetchStatus *code, int *http_code) = 0;

    /// Reset after transfer done, for retrying for exemple.
    virtual void reset() = 0;

    // Callbacks

    // A function to create the first buffer (typically for prepending
    // a wav header to a raw pcm stream. If set this is called from
    // the first curl write callback, before processing the curl data,
    // so this happens at a point where the client may have had a look
    // at the headers).
    virtual void setBuf1GenCB(std::function<bool(std::string& buf,void*,int)>) {
    }
    // Called when the network transfer is done
    void setEOFetchCB(std::function<void(bool ok, u_int64_t count)>) {
    }
    // Called every time we get new data from the remote
    void setFetchBytesCB(std::function<void(u_int64_t count)>) {
    }
};

#endif /* _MEDIAFETCH_H_INCLUDED_ */
