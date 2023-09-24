"""
PanPipe package
Copyright 2019,2020 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import io, sys, getopt, operator
from panpipe_ppl_lib import *

##################################################
class processdep_data:
    def __init__(self):
        self.deptype=None
        self.processname=None

##################################################
def take_pars():
    flags={}
    values={}
    flags["p_given"]=False
    flags["r_given"]=False
    flags["g_given"]=False
    flags["d_given"]=False
    values["verbose"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"p:rgdv",["pfile=","print-reord","print-graph","print-deps","verbose"])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-p", "--pfile"):
                values["pfile"] = arg
                flags["p_given"]=True
            elif opt in ("-r", "--print-reord"):
                flags["r_given"]=True
            elif opt in ("-g", "--print-graph"):
                flags["g_given"]=True
            elif opt in ("-d", "--print-deps"):
                flags["d_given"]=True
            elif opt in ("-v", "--verbose"):
                flags["verbose"]=True
    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["p_given"]==False):
        print("Error! -p parameter not given", file=sys.stderr)
        sys.exit(2)

    if(flags["r_given"] and flags["g_given"]):
        print("Error! -r and -g options cannot be given simultaneously", file=sys.stderr)
        sys.exit(2)

    if(flags["r_given"] and flags["d_given"]):
        print("Error! -r and -d options cannot be given simultaneously", file=sys.stderr)
        sys.exit(2)

    if(flags["g_given"] and flags["d_given"]):
        print("Error! -g and -d options cannot be given simultaneously", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("pipe_check     -p <string> [-r|-g|-d] [-v]", file=sys.stderr)
    print("", file=sys.stderr)
    print("-p <string>    Pipeline file", file=sys.stderr)
    print("-r             Print reordered pipeline", file=sys.stderr)
    print("-g             Print pipeline in graphviz format", file=sys.stderr)
    print("-d             Print dependencies for each process", file=sys.stderr)
    print("-v             Verbose mode", file=sys.stderr)

##################################################
def process_pars(flags,values):
    config_entries = extract_config_entries(values["pfile"])
    entries_lineno,process_entries = extract_process_entries(values["pfile"])
    multiattempt_processes = extract_processes_with_multiattempt(process_entries)
    deps_syntax_ok,processdeps_sep,processdeps_map = extract_processdeps_info(entries_lineno,process_entries)
    if(not deps_syntax_ok):
       print("Process dependencies are not syntactically correct", file=sys.stderr)
       return 1
    if(not snames_valid(processdeps_map)):
       print("Process names are not valid", file=sys.stderr)
       return 1
    ordered_process_entries = []
    if(processdeps_correct(entries_lineno,process_entries,multiattempt_processes,processdeps_map,ordered_process_entries)):
        print("Pipeline file is correct", file=sys.stderr)
        if(flags["r_given"]):
            print_entries(config_entries,ordered_process_entries)
        elif(flags["g_given"]):
            print_graph(ordered_process_entries,processdeps_sep,processdeps_map)
        elif(flags["d_given"]):
            print_deps(ordered_process_entries,processdeps_map)
    else:
        print("Pipeline file is not correct", file=sys.stderr)
        return 1

##################################################
def main(argv):
    # take parameters
    (flags,values) = take_pars()

    # check parameters
    check_pars(flags,values)

    # process parameters
    success = process_pars(flags,values)

    exit(success)

if __name__ == "__main__":
    main(sys.argv)
