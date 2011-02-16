import os, sys, optparse, time, mimetypes
import multiprocessing, threading, random, Queue
import urllib, urllib2, codecs
import logging, utils

global_proxy_username   = None
global_proxy_password   = None

def logger_maker():
    msgqueue = Queue.Queue()
    class LogThread(threading.Thread):
        def run(self):
            while True:
                values = msgqueue.get()
                for val in values: print val,
                print 
                msgqueue.task_done()
    LogThread().start()

    def logger_func(*args):
        msgqueue.put(args)
    return logger_func

LOG = utils.logger_maker()

def get_server_root():
    """
    Returns the root folder where this server script is running from.
    """
    return os.path.dirname(os.path.abspath(__file__))

def get_file_from_server(filename):
    return os.path.join(get_server_root(), filename)

def chunk_handler_to_file(filename):
    """
    Writes chunks as they are read from a url to a particular file.
    """
    filehandle = open(filename, "wb")
    def chunk_handler(chunk, chunk_len, chunk_time = None):
        if chunk_len == 0:
            # no more data, close file
            filehandle.close()
        else:
            filehandle.write(chunk)
    return chunk_handler

def get_mirror_list(list_url = "http://cygwin.com/mirrors.lst"):
    contents, time_taken = open_url(list_url)
    contents = contents.split("\n")
    return [c.split(";") for c in contents if c], time_taken

def open_url(url, chunk_size = -1, *chunk_handlers):
    """
    Open a URl and returns the reponse along with the time taken to fetch
    the contents of the url.
    """

    def register_proxy(url):
        """
        Register proxy usage for a particular URL.
        This is Crap!  We want this to be available to all urls (or provide
        exception lists for urls) instead of having to do this for each and
        every url we access.
        Needs to be fixed!
        """
        if os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy'):
            passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
            passman.add_password(None, url, get_proxy_username(), get_proxy_password())

            import ntlm
            from ntlm import HTTPNtlmAuthHandler
            auth_NTLM = HTTPNtlmAuthHandler.ProxyNtlmAuthHandler(passman)
            opener = urllib2.build_opener(auth_NTLM)
            urllib2.install_opener(opener)

    register_proxy(url)
    before = time.time()
    response = urllib2.urlopen(url)

    if chunk_size <= 0 or not chunk_handlers:
        # read the entire response and return it
        return response.read(), time.time() - before
    else:
        time1 = time.time()
        data = response.read(chunk_size)
        while len(data) > 0:
            time2 = time.time()
            for handler in chunk_handlers:
                handler(data, len(data), time2 - time1)
            time1 = time2
            data = response.read(chunk_size)

        # notify data finished
        for handler in chunk_handlers: handler(data, 0, None)

def get_proxy_username():
    global global_proxy_username
    if not global_proxy_username:
        global_proxy_username      = "%s\%s" % (os.environ['USERDOMAIN'], os.environ["USERNAME"])
    if not global_proxy_username:
        global_proxy_username = raw_input("Proxy Username: ")
    return global_proxy_username

def get_proxy_password():
    global global_proxy_password
    if not global_proxy_password:
        global_proxy_password = raw_input("Proxy Password: ")
    return global_proxy_password

def pkg_compare_by_selected(pkg1, pkg2):
    return pkg1['selected'] - pkg2['selected']

def pkg_compare_by_size(pkg1, pkg2):
    return pkg1['main']['install_size'] - pkg2['main']['install_size']

def pkg_compare_by_progress(pkg1, pkg2):
    return pkg1['progress']['completed_pct'] - pkg2['progress']['completed_pct']

def pkg_compare_by_name(pkg1, pkg2):
    return cmp(pkg1['name'], pkg2['name'])

pkg_sort_functions = {
    'selected': pkg_compare_by_selected,
    'size': pkg_compare_by_size,
    'progress': pkg_compare_by_progress,
    'name': pkg_compare_by_name,
};

