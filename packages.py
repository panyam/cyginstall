import os, sys, optparse, time, mimetypes
import multiprocessing, threading, random, Queue
import urllib, urllib2, codecs
import logging, utils, constants

def read_package_contents(package_file):
    setup_contents  = open(package_file).read().split("\n")
    packages        = []
    curr_package    = None
    multiline       = False
    attrib_name     = None
    attrib_value    = None
    attrib_complete = False
    group_type      = "main"
    curr_package_name   = ""
    for line in setup_contents:
        line = line.strip()
        if line.startswith("#") or not line:
            continue

        if line.startswith("@"):    # starting new package
            if curr_package: # add previous package if any
                packages.append(curr_package)

            # reset state
            multiline       = False
            group_type      = "main"
            curr_package    = { group_type: {}}
            attrib_name     = None
            attrib_value    = None
            attrib_complete = False
            curr_package_name   = line[1:].strip()
            curr_package['name'] = curr_package_name
            curr_package[group_type]['name'] = curr_package_name
            curr_package[group_type]['install_size'] = 0
        else:
            # get attributes - each attribute is of the form:
            # attrib: value
            # where value can be multi lined (quoted).
            if multiline:
                # see if the current line ends with a "
                if line.endswith('"'):
                    attrib_value += " " + line[:-1]
                    attrib_complete = True
                else:
                    attrib_value += " " + line
            else:
                # see if line has <.....>:
                colpos = line.find(": ")
                if colpos > 0:
                    attrib_name = line[:colpos]
                    line        = line[colpos + 1:].strip()
                    multiline   = line.startswith('"')
                    if multiline:
                        attrib_value = line[1:].strip()
                        # see if line also ends with a " in which case this
                        # is also the last line.
                        if attrib_value.endswith('"'):
                            attrib_value    = attrib_value[:-1]
                            multiline       = False
                    else:
                        attrib_value = line.strip()
                    attrib_complete = not multiline
                else:
                    if line[0] == '[' and line[-1] == ']':
                        # add to a particular group instead of main
                        group_type = line[1:-1]
                        curr_package[group_type] = {}
                    else:
                        # do nothing
                        utils.LOG("Ignoring Line: ", line)

            if attrib_name and attrib_complete and curr_package:
                if attrib_name in ("source", "install"):
                    file_source, file_size, file_md5 = attrib_value.split()
                    curr_package[group_type][attrib_name + "_file"] = file_source
                    curr_package[group_type][attrib_name + "_size"] = int(file_size)
                    curr_package[group_type][attrib_name + "_md5"]  = file_md5
                elif attrib_name in ("category", "requires"):
                    # then split as list of entries
                    curr_package[group_type][attrib_name] = attrib_value.split()
                else:
                    # raw string
                    curr_package[group_type][attrib_name]   = attrib_value
                attrib_name     = None
                attrib_value    = None
                attrib_complete = False
                multiline       = False
                

    if curr_package:
        packages.append(curr_package)

    return packages

class PackageList(object):
    """
    A class to manage packages being installed or that have been installed.
    Each package will have info like:
        name, description (short and long), version, mirror obtained from,
        size etc
    """
    def __init__(self, package_list_file):
        if not os.path.isfile(package_list_file):
            open(package_list_file, "w"). write("{}")
        self.package_list_file  = package_list_file
        try:
            self.package_list   = eval(open(package_list_file).read())
            # ensure all packages marked as downloading are reverted to
            # queued
            for pkg_name in self.package_list:
                package = self.package_list[pkg_name]
                if package['progress']['status'] == constants.PROG_DOWNLOADING or   \
                    package['progress']['completed_bytes'] < self.get_package_size(package):
                    package['progress']['status'] = constants.PROG_QUEUED
        except SyntaxError, se:
            utils.LOG("Syntax Error in %s.  Ignoring package list file." % mirror_list_file)
            self.package_list   = { }
        self.no_saving          = False
        self.list_mutex         = threading.RLock()

    def critical_section(target):
        def func(obj, *args, **kwargs):
            obj.list_mutex.acquire()
            out = target(obj, *args, **kwargs)
            obj.list_mutex.release()
            return out
        return func

    def get_package_size(self, package, source = False):
        """
        Gets the size of the file that is to be downloaded for the package.
        """
        if source or 'install_file' not in package['main']:
            return package['main'].get('source_size', 0)
        else:
            return package['main']['install_size']

    def get_package_file(self, package, source = False):
        if source or 'install_file' not in package['main']:
            return package['main'].get('source_file', None)
        else:
            return package['main']['install_file']

    def get_packages(self):
        return self.package_list

    def contains(self, pkg_name):
        """
        Tells if a particular package exists.
        """
        return pkg_name in self.package_list

    @critical_section
    def add_package(self, name, package):
        """
        Adds a new package to the list.
        """
        self.package_list[name] = package
        if 'mirrors' not in self.package_list[name]:
            self.package_list[name]['selected'] = False
            self.package_list[name]['progress'] = {
                'mirror': None, 
                'completed_pct': 0,
                'completed_bytes': 0,
                'status': constants.PROG_QUEUED
            }
        self.save()

    @critical_section
    def select_packages(self, packages, select):
        """
        Selects or unselects a set of package for installation.
        """
        for package in packages:
            if package not in self.package_list:
                self.package_list[package] = {'name': package, 'selected': False}
            if self.package_list[package]['selected'] != select:
                self.package_list[package]['selected'] = select
        self.save()

    # These methods enable and disable saving (so we can avoid saving over
    # small changes)
    def disable_saves(self): self.no_saving = True
    def enable_saves(self):
        self.no_saving = False
        self.save()

    def save(self, override_disable = False):
        """
        Saves the package list.
        """
        if override_disable or not self.no_saving:
            outfile = open(self.package_list_file, "w")
            outfile.write("{\n")
            for pkg_name in self.package_list:
                outfile.write("    '%s': %s,\n" % (pkg_name, str(self.package_list[pkg_name])))
            outfile.write("}\n")
            outfile.close()
