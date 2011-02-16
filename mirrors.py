import os, sys, optparse, time, mimetypes
import multiprocessing, threading, random, Queue
import urllib, urllib2, codecs
import logging, utils, constants

class MirrorList(object):
    """
    A convinient class to maintain the list of mirrors and update the
    status of the mirrors in run time.
    """
    def __init__(self, mirror_list_file):
        try:
            mirror_list = eval(open(mirror_list_file).read())
        except SyntaxError, se:
            utils.LOG("Syntax Error in %s.  Ignoring mirror list file." % mirror_list_file)
            mirror_list = { }

        self.active_mirrors     = [mirror for mirror in mirror_list
                                                       if mirror_list[mirror]['active']]
        self.mirror_list_file   = mirror_list_file
        self.mirror_list        = mirror_list
        self.list_mutex         = threading.Lock()

    def update_mirror(self, mirror, **kwargs):
        """
        Updates info about a particular mirror.
        """
        utils.LOG("\nUpdating Mirror: ", mirror, ", With Args: ", kwargs)
        changed = False
        self.list_mutex.acquire()

        for param in kwargs:
            utils.LOG("Updating Param, Value: ", param, kwargs[param])
            if param not in self.mirror_list[mirror] or \
                    self.mirror_list[mirror][param] != kwargs[param]:
                changed = True
                self.mirror_list[mirror][param] = kwargs[param]

        if self.mirror_list[mirror]['active'] and mirror not in self.active_mirrors:
            self.active_mirrors.append(mirror)
        elif mirror in self.active_mirrors and not self.mirror_list[mirror]['active']:
            self.active_mirrors.remove(mirror)

        # save the mirror list if atleast one param changed
        if changed:
            open(self.mirror_list_file, "w").write(str(self.mirror_list))

        self.list_mutex.release()

    def get_mirror(self, mirror):
        """
        Gets info about a particular mirror.
        """
        return self.mirror_list[mirror]

    def get_active_mirrors(self):
        return [self.mirror_list[name] for name in self.active_mirrors]

    def get_mirrors(self):
        return self.mirror_list

    def acquire_mirror(self):
        """
        Acquires a mirror for downloading a package.
        Used to maintain a round-robin list.
        """
        return random.choice(self.get_active_mirrors())

    def release_mirror(self, mirror):
        """
        Releases a mirror that has been used for downloading.
        """
        # Does nothing for now.  
        # When implemented it will assist in round robining.  For now we
        # are selecting a random active mirror and hopefully this should
        # give a balanced spread across all the mirrors.
        pass
