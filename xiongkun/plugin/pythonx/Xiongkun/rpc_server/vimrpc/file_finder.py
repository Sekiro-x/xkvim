import os
import sys
import json
import time
from .decorator import *
from .functions import KillablePool
from .fuzzy_list import FuzzyList
from .utils import GetSearchFiles

class FileFinder:
    def __init__(self, queue, ppool):
        self.queue = queue
        self.ppool = ppool
        self.root = None
        self.fuzzy = FuzzyList(self.queue, ppool)
        pass

    @server_function
    def set_root(self, rootpath, force=False):
        if not force and self.root == rootpath: 
            return self.files[:17]
        self.root = rootpath
        self.files = GetSearchFiles(self.root)
        # TODO: find files and reset it.
        self.fuzzy.set_items(-1, "filefinder", self.files)
        return self.files[:17]

    # transfer only
    def search(self, id, name, search_text):
        return self.fuzzy.search(id, 'filefinder', search_text)

if __name__ == "__main__":
    test_main()
