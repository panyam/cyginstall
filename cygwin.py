import os, sys, optparse, time, mimetypes
import multiprocessing, threading, random, Queue
import urllib, urllib2, codecs
import logging, utils, mirrors, packages, constants
from SocketServer import ThreadingMixIn
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

reload(packages)
reload(mirrors)
reload(constants)
reload(utils)

"""
This little app allows you to manage the cygwin download process in a
much more flexible and customizable way than the cygwin setup itself.

With this tool, a download process can be resumed any time.  Also it is
dynamic in that it will try to download multiple packages in parallel from
multiple mirrors and at the same time will pick the fastest mirrors based
on the mirrors' performance history.
"""

# proxy_host = "http://proxy-syd1.macbank:8080"):

class TestThread(threading.Thread):
    def __init__(self, queue):
        self.queue = queue
        self.stopped = False
        threading.Thread.__init__(self)

    def run(self):
        while not self.stopped:
            try:
                next = self.queue.get(True, 0.1)
                print "Next Item: ", next
            except Queue.Empty:
                print "Nothing found, retrying..."
                pass
        print "Thread [%s] finished." % self.getName()

class DownloaderThread(threading.Thread):
    """
    The thread that takes care of downloads of the packages.  Each package
    to be downloaded is put into the download queue in the context and the
    thread read them off one by one.
    """
    def __init__(self, context):
        threading.Thread.__init__(self)
        self.context = context
        self.stopped = False

    def run(self):
        while not self.stopped:
            # grab the next package if any
            try:
                package = self.context.download_queue.get(True, 0.1)
                if package['selected']  and self.context.package_list.get_package_file(package)  \
                        and package['progress']['status'] not in                \
                                (constants.PROG_COMPLETED, constants.PROG_DOWNLOADING):
                    package['progress']['status'] = constants.PROG_DOWNLOADING
                    # then download it
                    # pick a random mirror first - for now we are picking the first
                    # one but we really need to load balance across multiple
                    # mirrors
                    mirror = self.context.mirror_list.acquire_mirror()
                    self.download_package(mirror, package)
                    self.context.mirror_list.release_mirror(mirror)
                else:
                    utils.LOG("Package already downloaded: ", package['main']['name'])
            except Queue.Empty:
                pass
        print "Downloader Thread [%s] finished." % self.getName()

    def request_stop(self):
        """
        Requests that the thread be stopped.  After the current download
        has finished, it will be stopped.
        """
        utils.LOG("%s stop requested." % self.getName())
        self.stopped = True

    def download_package(self, mirror, package):
        mirror_folder   = self.context.get_mirror_folder(mirror['path'])
        install_path    = self.context.package_list.get_package_file(package)
        install_dir     = os.path.join(mirror_folder, os.path.dirname(install_path))
        install_file    = os.path.join(mirror_folder, install_path)
        # utils.LOG("Install Dir: ", install_dir)
        # utils.LOG("Install File: ", install_file)
        if not os.path.isdir(install_dir):
            os.makedirs(install_dir)

        package_url = mirror['path'] + "/" + install_path
        utils.LOG("Downloading: ", package_url)

        package['progress']['completed_bytes']  = 0
        package['progress']['completed_pct']    = 0
        timebefore = time.time()
        def update_package_progress(chunk, chunk_len, chunk_time = None):
            if chunk_len == 0:
                utils.LOG("  ++++++++++++++  Package %s download complete." % package['name'])
                # and notify the post download queue that we are done...
                self.context.download_queue.task_done()
                self.context.post_download_queue.put({'mirror': mirror,
                                                      'package': package,
                                                      'time': time.time() - timebefore})
            else:
                package['progress']['completed_bytes'] += chunk_len

                package_size = self.context.package_list.get_package_size(package)
                completed_pct = float(package['progress']['completed_bytes']) / float(package_size)

                package['progress']['completed_pct'] = int(100 * completed_pct)
                utils.LOG("=== Package %s - %d out of %d downloaded..." %
                                (package['name'],
                                package['progress']['completed_bytes'],
                                package_size))

        # save url to file
        utils.open_url(package_url, constants.DEFAULT_CHUNK_SIZE,
                 utils.chunk_handler_to_file(install_file),
                 update_package_progress)

class PostDownloaderThread(threading.Thread):
    """
    After a package has finished downloading, the DownloaderThread puts the
    package and other details (like time taken etc) into the out_queue.
    This thread processes this data in this queue.
    """
    def __init__(self, context):
        threading.Thread.__init__(self)
        self.context = context
        self.stopped = False

    def run(self):
        while not self.stopped:
            try:
                # grab the next package if any
                data = self.context.post_download_queue.get(True, 0.1)
                package = data['package']
                if package['selected']:
                    # flag is it completed if its completed_bytes >= install_size
                    # and also set the mirror from which it had been downloaded
                    mirror = data['mirror']
                    package['progress']['mirror'] = mirror['path']
                    package_size = self.context.package_list.get_package_size(package)
                    if package['progress']['completed_bytes'] >= package_size:
                        package['progress']['status'] = constants.PROG_COMPLETED

                    # save!
                    self.context.package_list.save()

                    # save package data and status
                self.context.post_download_queue.task_done()
            except Queue.Empty:
                pass
        print "Post Downloader Thread [%s] finished." % self.getName()

class CygwinContext(object):
    """
    Holds context and data for the downloader.
    """
    def __init__(self, download_folder = ".",
                 num_threads = constants.DEFAULT_NUM_THREADS):
        """
        Called to initialise the context to a particular folder.
        This must be called before the server is created.
        """
        utils.LOG("Preparing download folder...")
        self.num_threads            = num_threads
        self.download_queue         = Queue.Queue()
        self.post_download_queue    = Queue.Queue()
        download_folder             = os.path.abspath(download_folder)
        self.download_folder        = download_folder
        if not os.path.isdir(download_folder):
            # create install folder if it does not exist
            utils.LOG("Creating download folder...")
            os.makedirs(download_folder)
        else:
            utils.LOG("Download folder already exists...")

        # update mirror list
        mirror_list_file = os.path.join(download_folder, "mirrors.lst")
        if not os.path.isfile(mirror_list_file):
            # get mirror list if it is not already there
            utils.LOG("Downloading mirror.lst...")
            mirror_list, time_taken = utils.get_mirror_list()
            outfile = open(mirror_list_file, "w")
            outfile.write("{\n")
            for mirror in mirror_list:
                utils.LOG("Writing Mirror: ", mirror)
                outfile.write("'%s': {" % mirror[0])
                outfile.write("'path': '%s', " % mirror[0])
                outfile.write("'host': '%s', " % mirror[1])
                outfile.write("'location': '%s', " % ",".join(mirror[2:]))
                outfile.write("'active': False, ")
                outfile.write("'bytes_loaded': 0, ")
                outfile.write("'time_spent': 0, ")
                outfile.write("},\n")
            outfile.write("}")
            outfile.close()
        else:
            utils.LOG("Mirror list file exists...")
        self.mirror_list    = mirrors.MirrorList(mirror_list_file)

        # update selected packages list
        self.package_list = packages.PackageList(os.path.join(download_folder, "packages.ini"))

        # now check the files already downloaded to see if the sizes match
        """
        for mirror in os.listdir(download_folder):
            if mirror in ["mirrors.lst", "packages.ini"]:
                continue
            for package in os.listdir(download_folder + "/" + mirror):
                if package in ["setup.ini"]:
                    continue
                # read package to see
        """

    def get_mirror_folder(self, mirror):
        """
        Gets the mirror folder (and creates it if it does not exist).
        """
        mirror_folder = os.path.abspath(os.path.join(self.download_folder, urllib.quote_plus(mirror)))
        if not os.path.isdir(mirror_folder):
            print "Creating mirror folder: ", mirror_folder
            os.makedirs(mirror_folder)
        return mirror_folder
        
    def get_mirror(self, mirror):
        """
        Gets info about a particular mirror.
        """
        return self.mirror_list.get_mirror(mirror)

    def get_mirrors(self):
        return self.mirror_list.get_mirrors()

    def get_packages(self):
        return self.package_list.get_packages()

    def select_packages(self, package_names, select):
        """
        Selects whether a package is to be installed or not.
        """
        self.package_list.select_packages(package_names, select)

    def activate_mirror(self, mirror, activate):
        """
        Activates or deactivates a mirror.
        """
        utils.LOG("Mirror: ", mirror, ", Activate: ", activate)
        self.mirror_list.update_mirror(mirror, active = activate)

    def get_mirror_contents(self, mirror, refresh = False):
        """
        Gets the contents of (files hosted by) a mirror, refreshing or
        refetching the setup.bz2 file if necessary.
        Note that when this happens its throughput is also recorded.
        """
        mirror_folder = self.get_mirror_folder(mirror)

        # check if setup.ini at the mirror exists
        mirror_setup_ini = os.path.join(mirror_folder, "setup.ini")
        mirror_setup_exists = os.path.isfile(mirror_setup_ini)
        if refresh or (not mirror_setup_exists):
            utils.LOG("Mirror setup exists: ", mirror_setup_exists, refresh)
            utils.LOG("Downloading setup.bz2... ")
            try:
                setup_file_contents, time_taken = utils.open_url(mirror + "/setup.bz2")

                # TODO: Try downloading setup.ini file if setup.bz2 fails

                # open(mirror_folder + "/setup.bz2", "wb").write(setup_file_contents)
                # now decode it
                decoder = codecs.getdecoder("bz2")
                contents, length = decoder(setup_file_contents)
                open(mirror_setup_ini, "w").write(contents)

                # reset the mirror's throughput 
                self.mirror_list.update_mirror(mirror,
                                                bytes_loaded = length,
                                                time_spent = time_taken,
                                                health = int(length / time_taken))
            except:
                self.mirror_list.update_mirror(mirror, health = "Down")
                return None

        # Load setup.ini and return its contents
        pkgs = packages.read_package_contents(mirror_setup_ini)
        self.mirror_list.update_mirror(mirror, num_packages = len(pkgs))

        # update the package contents - ie which packages are in
        # which mirrors etc
        self.package_list.disable_saves()

        for pkg_obj in pkgs:
            pkg_name = pkg_obj['main']['name']
            if not self.package_list.contains(pkg_name):
                self.package_list.add_package(pkg_name, pkg_obj)

        self.package_list.enable_saves()

        return pkgs


class CygwinHTTPServer(ThreadingMixIn, HTTPServer):
    """
    Customised http server to keep track of a few document roots to server
    static files from when the path matches a particular prefix.
    """
    def initialise(self, prefix, path, context):
        """
        Sets the doc root for a particular prefix.
        """
        self.context = context
        if not hasattr(self, "doc_roots"):
            self.doc_roots = {}
        # strip trailing slashes
        while path.endswith("/"): path = path[:-1]
        self.doc_roots[prefix] = path

        # now start the threads
        self.post_download_queue = Queue.Queue()
        self.post_downloader_thread = PostDownloaderThread(self.context)
        self.post_downloader_thread.start()

        self.download_queue = Queue.Queue()
        self.downloader_threads = [DownloaderThread(self.context) for i in xrange(0, context.num_threads)]
        for thread in self.downloader_threads:
            thread.start()

    def do_cleanup(self):
        utils.LOG("Closing Server Socket...")
        self.socket.close()
        for thread in self.downloader_threads:
            thread.stopped = True
            thread.join()
        self.post_downloader_thread.stopped = True
        self.post_downloader_thread.join()

    def resume_downloads(self, orderby = None):
        """
        Resumes downloads.
        """
        # go through the server and add all packages not yet downloaded but
        # selected to the download queue
        pkgs = self.context.get_packages().values()
        if orderby:
            descending = orderby[0] == '-'
            if descending:
                orderby = orderby[1:]
            pkgs.sort(utils.pkg_sort_functions[orderby])
            if descending:
                pkgs.reverse()

        for package in pkgs:
            package_file = self.context.package_list.get_package_file(package)
            if package['selected']  and package_file and  package['progress']['status'] not in \
                                            (constants.PROG_COMPLETED, constants.PROG_DOWNLOADING):
                utils.LOG("Queueing Package: ", package['main']['name'])
                package['progress']['status'] = constants.PROG_QUEUED
                self.context.download_queue.put(package)

class CygwinHandler(BaseHTTPRequestHandler):
    def match_and_serve_static_file(self):
        """
        Tries to match a static prefix and if a match was found, a file at
        the folder corresponding to that prefix is served.
        """
        for prefix in self.server.doc_roots:
            if self.path.startswith(prefix):
                doc_root        = self.server.doc_roots[prefix]
                file_to_serve   = os.path.join(doc_root, self.path[len(prefix):])
                # serve out this file
                self.serve_file(file_to_serve)
                return True
        else:
            if self.path == "/":
                self.serve_template("templates/index.html")
                return True
        return False

    def serve_json(self, output):
        self.send_response(200)
        self.send_header('Content-type', "application/json")
        self.end_headers()
        import json
        self.wfile.write(json.dumps(output))
        
    def serve_template(self, template_file, values = {}):
        """
        Renders and serves the resulting template.
        """
        self.send_response(200)
        self.send_header('Content-type', "text/html")
        self.end_headers()

        from jinja2 import Template
        template = Template(open(utils.get_file_from_server(template_file)).read())
        rendered = template.render(**values)
        self.wfile.write(rendered)
    
    def serve_file(self, file_to_serve):
        """
        Serves a file as the response.
        """
        file_to_serve = os.path.abspath(file_to_serve)
        utils.LOG("--- File To Serve: ", file_to_serve)
        try:
            file_handle = open(file_to_serve)
        except:
            self.send_response(404, "File not found: %s" % self.path)
            return 

        self.send_response(200)
        content_type, encoding = mimetypes.guess_type(file_to_serve)
        if content_type:
            self.send_header('Content-type', content_type)
            self.end_headers()
        self.wfile.write(file_handle.read())
        file_handle.close()

    def do_GET(self):
        # do we match any static paths?
        cygcontext = self.server.context
        if not self.match_and_serve_static_file():
            # Handle urls here...
            if self.path.startswith("/mirrors/"):
                # return mirror list
                self.serve_json({'code': 0,
                                 'value': { 'mirrors': cygcontext.get_mirrors() }})
            elif self.path.startswith("/packages/"):
                # return package list
                self.serve_json({'code': 0,
                                 'value': { 'packages': cygcontext.get_packages() }})
            elif self.path.startswith("/mirror/contents/?"):
                query_params = self.path[len("/mirror/contents/?"):].strip()
                if query_params:
                    query_params = [map(urllib.unquote_plus, qp.split('='))
                                                for qp in query_params.split("&")]
                    query_params = dict(query_params)
                else:
                    query_params = {}
                mirror  = query_params['mirror']
                refresh = query_params.get('refresh', False)

                # see if the mirror folder exists
                contents = cygcontext.get_mirror_contents(mirror, refresh)
                if contents:
                    themirror = cygcontext.get_mirror(mirror)
                    self.serve_json({'code': 0,
                                     'value': {
                                     'contents': contents,
                                     'health': themirror['health'],
                                     'num_packages': themirror['num_packages']}})
                else:
                    self.serve_json({'code': -1, 'value': "Unable to fetch contents.  Mirror may be down."})
            else:
                # invalid url
                self.send_response(404, "Invalid URL: %s" % self.path)
                return 

    def do_POST(self):
        path            = self.path
        content_length  = int(self.headers['Content-length'])
        contents        = self.rfile.read(content_length).strip()
        cygcontext      = self.server.context

        if contents:
            contents = [map(urllib.unquote_plus, c.split('=')) for c in contents.split("&")]
            contents_dict = dict(contents)
        else:
            contents_dict = {}

        if path.startswith("/mirrors/activate") or path.startswith("/mirrors/deactivate"):
            cygcontext.activate_mirror(contents_dict['mirror'], path.startswith("/mirrors/activate"))
            self.send_response(200, "OK")
        elif path.startswith("/packages/select") or path.startswith("/packages/unselect"):
            package_names = eval(contents_dict['packages'])
            print "Package Names: ", package_names
            cygcontext.select_packages(package_names, path.startswith("/packages/select"))
            self.serve_json({'code': 0, 'value': "OK"})
        elif path.startswith("/downloads/start"):
            # start the downloads if not already happening
            self.server.resume_downloads(contents_dict.get('orderby', None))
            self.serve_json({'code': 0, 'value': "OK"})

class CygwinDownloader(object):
    def __init__(self, download_folder = "cyginstall",
                 port = 8888,
                 num_threads = constants.DEFAULT_NUM_THREADS):
        self.port = port
        self.server = CygwinHTTPServer(("", port), CygwinHandler)
        self.server.initialise("/static/",
                               utils.get_file_from_server("static"),
                               CygwinContext(download_folder, num_threads))

    def start(self):
        """
        Starts the main web server app that manages cygwin installs.
        """
        try:
            print "Starting server socket..."
            self.server.serve_forever()
        except KeyboardInterrupt:
            print "KeyBoard Interrupt..."
        finally:
            print "Exiting..."
        self.server.do_cleanup()

def usage():
    print "%s <download_folder> <http port>"
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) <= 3: usage()
    CygwinDownloader(sys.argv[1], int(sys.argv[2])).start()

