#!/usr/bin/env python
#
# Copyright (C) 2017 J.F.Dockes
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

import sys
import os
import conftree
import threading
import subprocess
import time
from timeit import default_timer as timer

from rwlock import ReadWriteLock
import uprclfolders
import uprcltags
import uprcluntagged
import uprclsearch
import uprclhttp
import uprclindex
from uprclcontrol import runbottle

from uprclutils import uplog, findmyip, stringToStrings

# The recoll documents
g_rcldocs = []
g_pathprefix = ""
g_httphp = ""
g_dblock = ReadWriteLock()
g_rclconfdir = ""

# Create or update Recoll index, then read and process the data.
def _update_index():
    uplog("Creating/updating index in %s for %s" % (g_rclconfdir, g_rcltopdirs))

    # We take the writer lock, making sure that no browse/search
    # thread are active, then set the busy flag and release the
    # lock. This allows future browse operations to signal the
    # condition to the user instead of blocking (if we kept the write
    # lock).
    global g_initrunning
    g_dblock.acquire_write()
    g_initrunning = True
    g_dblock.release_write()
    
    start = timer()
    uprclindex.runindexer(g_rclconfdir, g_rcltopdirs)
    # Wait for indexer
    while not uprclindex.indexerdone():
        time.sleep(.5)
    fin = timer()
    uplog("Indexing took %.2f Seconds" % (fin - start))

    global g_rcldocs
    g_rcldocs = uprclfolders.inittree(g_rclconfdir, g_httphp, g_pathprefix)
    uprcltags.recolltosql(g_rcldocs)
    uprcluntagged.recoll2untagged(g_rcldocs)

    g_dblock.acquire_write()
    g_initrunning = False
    g_dblock.release_write()


# This runs in a thread because of the possibly long index initialization.
def _uprcl_init_worker():

    #######
    # Acquire configuration data.
    
    global g_pathprefix
    # pathprefix would typically be something like "/uprcl". It's used
    # for dispatching URLs to the right plugin for processing. We
    # strip it whenever we need a real file path
    if "UPMPD_PATHPREFIX" not in os.environ:
        raise Exception("No UPMPD_PATHPREFIX in environment")
    g_pathprefix = os.environ["UPMPD_PATHPREFIX"]
    if "UPMPD_CONFIG" not in os.environ:
        raise Exception("No UPMPD_CONFIG in environment")
    upconfig = conftree.ConfSimple(os.environ["UPMPD_CONFIG"])

    global g_httphp
    g_httphp = upconfig.get("uprclhostport")
    if g_httphp is None:
        ip = findmyip()
        g_httphp = ip + ":" + "9090"
        uplog("uprclhostport not in config, using %s" % g_httphp)

    global g_rclconfdir
    g_rclconfdir = upconfig.get("uprclconfdir")
    if g_rclconfdir is None:
        uplog("uprclconfdir not in config, using /var/cache/upmpdcli/uprcl")
        g_rclconfdir = "/var/cache/upmpdcli/uprcl"

    global g_rcltopdirs
    g_rcltopdirs = upconfig.get("uprclmediadirs")
    if g_rcltopdirs is None:
        raise Exception("uprclmediadirs not in config")

    pthstr = upconfig.get("uprclpaths")
    if pthstr is None:
        uplog("uprclpaths not in config")
        pthlist = stringToStrings(g_rcltopdirs)
        pthstr = ""
        for p in pthlist:
            pthstr += p + ":" + p + ","
        pthstr = pthstr.rstrip(",")
    uplog("Path translation: pthstr: %s" % pthstr)
    lpth = pthstr.split(',')
    pathmap = {}
    for ptt in lpth:
        l = ptt.split(':')
        pathmap[l[0]] = l[1]


    host,port = g_httphp.split(':')
    if True:
        # Running the server as a thread. We get into trouble because
        # something somewhere writes to stdout a bunch of --------.
        # Could not find where they come from, happens after a sigpipe
        # when a client closes a stream. The --- seem to happen before
        # and after the exception strack trace, e.g:
        # ----------------------------------------
        #   Exception happened during processing of request from ('192...
        #   Traceback...
        #   [...]
        # error: [Errno 32] Broken pipe
        # ----------------------------------------
        # 
        # **Finally**: found it: the handle_error SocketServer method
        # was writing to stdout.  Overriding it should have fixed the
        # issue. Otoh the separate process approach works, so we kept
        # it for now
        httpthread = threading.Thread(target=uprclhttp.runHttp,
                                      kwargs = {'host':host ,
                                                'port':int(port),
                                                'pthstr':pthstr,
                                                'pathprefix':g_pathprefix})
        httpthread.daemon = True 
        httpthread.start()
    else:
        # Running the HTTP server as a separate process
        cmdpath = os.path.join(os.path.dirname(sys.argv[0]), 'uprclhttp.py')
        cmd = subprocess.Popen((cmdpath, host, port, pthstr,g_pathprefix),
                               stdin = open('/dev/null'),
                               stdout = sys.stderr,
                               stderr = sys.stderr,
                               close_fds = True)

    _update_index()

    uplog("Uprcl: init done")

def uprcl_init():
    # This lock and counter are used as a read/write lock 
    global g_initrunning
    g_initrunning = True
    initthread = threading.Thread(target=_uprcl_init_worker)
    initthread.daemon = True 
    initthread.start()
    # Start the control/config interface
    ctlthread = threading.Thread(target=runbottle)
    ctlthread.daemon = True 
    ctlthread.start()


def ready():
    g_dblock.acquire_read()
    if g_initrunning:
        return False
    else:
        return True

def start_update():
    if not ready():
        g_dblock.release_read()
        return
    idxthread = threading.Thread(target=_update_index)
    idxthread.daemon = True 
    # We need to release the reader lock before starting the index
    # update operation, so that there is a small window for
    # mischief. I would be concerned if this was a highly concurrent
    # or critical app, but here, not so much...
    g_dblock.release_read()
    idxthread.start()
 
