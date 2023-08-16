from __future__ import print_function
import json
import socket
import sys
import threading
from threading import Thread
from vimrpc.fuzzy_list import FuzzyList
from vimrpc.file_finder import FileFinder
from vimrpc.decorator import InQueue
from vimrpc.remote_fs import RemoteFS
from vimrpc.yiyan_server import Yiyan
from vimrpc.grep_search import GrepSearcher
from vimrpc.hoogle import HoogleSearcher
from vimrpc.configure import ProjectConfigure
import multiprocessing as mp
from log import log

class ProcessManager:
    def __init__(self):
        self.pools = {}

    def terminal_all(self): 
        for p in self.pools.values():
            p.terminal()
        self.pools.clear()

    def terminal(self, server):
        self.pools[id(server)].terminal()
        del self.pools[id(server)]

    def start_process(self, server, target, args):
        server_id = id(server)
        p = mp.Process(target=worker, args=args)
        p.start()
        server_process = self.pools.get(server_id, [])
        server_process.append(p)
        return p

class ServerCluster: 
    def __init__(self, mp_manager):
        self.process_manager = ProcessManager()
        self.queue = mp_manager.Queue()
        self.filefinder = FileFinder(self.queue, self.process_manager)
        self.remotefs = RemoteFS()
        self.fuzzyfinder = FuzzyList(self.queue, self.process_manager)
        self.yiyan = Yiyan(self.queue)
        self.grepfinder = GrepSearcher(self.queue, self.process_manager)
        self.hoogle = HoogleSearcher(self.queue)
        self.config = ProjectConfigure(self.queue)
        def keeplive(*a, **kw): 
            return [-1, True, 'ok']
        self.keeplive = keeplive
        self._stop = False

    def _QueueLoop(self, process_fn):
        log("[Server]: Start queue loop.")
        while not self._stop:
            try:
                output = self.queue.get(timeout=1)
                log(f"[Server]: Queue Get! {output}")
                process_fn(output)
            except Exception as e:
                continue

    def get_server_fn(self, name):
        name = name.strip()
        obj = self
        for f in name.split('.'): 
            if hasattr(obj, f): 
                obj = getattr(obj, f)
            elif isinstance(obj, dict) and f in obj:
                obj = obj.get(f, None)
            else:
                obj = None
        if callable(obj):
            return obj
        log("[Server]: don't found ", name, ", skip it.")
        return None

    def start_queue(self, sender):
        self.queue_thread = Thread(target=self._QueueLoop, args=[sender], daemon=True)
        self.queue_thread.start()

    def stop(self):
        self._stop = True
        self.queue_thread.join()

def printer_process_fn(output):
    print (output)
