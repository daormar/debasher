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

# Constants
NONE_PROCESS_DEP="none"

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
def entry_is_comment(entry):
    fields=entry.split()
    if len(fields)==0:
        return False
    elif fields[0][0]=="#":
        return True
    else:
        return False

##################################################
def entry_is_config(entry):
    fields=entry.split()
    if len(fields)==0:
        return False
    elif fields[0]=="#import":
        return True
    else:
        return False

##################################################
def entry_is_empty(entry):
    fields=entry.split()
    if len(fields)==0:
        return True
    else:
        return False

##################################################
def extract_process_name(entry):
    fields=entry.split()
    if len(fields)==0:
        return ""
    else:
        return fields[0]

##################################################
def get_dep_separator(pdeps_str):
    if ',' in pdeps_str and '?' in pdeps_str:
        return True,',?'
    elif ',' in pdeps_str:
        return False,','
    elif '?' in pdeps_str:
        return False,'?'
    else:
        return False,''

##################################################
def extract_process_deps(entry_lineno,entry):
    deps_syntax_ok=True
    # extract text field
    fields=entry.split()
    pdeps_str=""
    for f in fields:
        if f.find("processdeps=")==0:
            pdeps_str=f[len("processdeps="):]

    # Return empty list of process dependencies if corresponding field was
    # not found
    if len(pdeps_str)==0:
        return deps_syntax_ok,[]

    # Check that dependency separators (, and ?) are not mixed
    seps_mixed,separator=get_dep_separator(pdeps_str)
    if seps_mixed:
        deps_syntax_ok=False
        print("Error: dependency separators mixed in process dependency (",pdeps_str,") at line number",entry_lineno, file=sys.stderr)
        return deps_syntax_ok,[]

    # create list of process dependencies
    pdeps_list=[]
    if(separator==''):
        pdeps_fields=[pdeps_str]
    else:
        pdeps_fields=pdeps_str.split(separator)
    for pdep in pdeps_fields:
        if pdep!=NONE_PROCESS_DEP:
            pdep_fields=pdep.split(":")
            if(len(pdep_fields)==2 and pdep_fields[1]!=''):
                data=processdep_data()
                data.deptype=pdep_fields[0]
                data.processname=pdep_fields[1]
                pdeps_list.append(data)
            else:
                deps_syntax_ok=False
                print("Error: incorrect definition of process dependency (",pdeps_str,") at line number",entry_lineno, file=sys.stderr)

    return deps_syntax_ok,separator,pdeps_list

##################################################
def extract_config_entries(pfile):
    process_entries=[]
    file = open(pfile, 'r')
    # read file entry by entry
    for entry in file:
        entry=entry.strip("\n")
        if entry_is_config(entry):
            process_entries.append(entry)

    return process_entries

##################################################
def extract_process_entries(pfile):
    entries_lineno=[]
    process_entries=[]
    file = open(pfile, 'r')
    # read file entry by entry
    lineno=1
    for entry in file:
        entry=entry.strip("\n")
        if not entry_is_comment(entry) and not entry_is_empty(entry):
            process_entries.append(entry)
            entries_lineno.append(lineno)
        lineno=lineno+1

    return entries_lineno,process_entries

##################################################
def extract_time_value(entry):
    fields=entry.split()
    i=0
    found=False
    value=""
    while i<len(fields) and not found:
        if fields[i].find("time=")==0:
            found=True
            value=fields[i][5:]
        else:
            i=i+1
    return value

##################################################
def extract_mem_value(entry):
    fields=entry.split()
    i=0
    found=False
    value=""
    while i<len(fields) and not found:
        if fields[i].find("mem=")==0:
            found=True
            value=fields[i][4:]
        else:
            i=i+1
    return value

##################################################
def str_contains_commas(str):
    if(',' in str):
        return True
    else:
        return False

##################################################
def extract_processes_with_multiattempt(process_entries):
    multiattempt_processes=set()
    for i in range(len(process_entries)):
        sname=extract_process_name(process_entries[i])
        time_value=extract_time_value(process_entries[i])
        mem_value=extract_mem_value(process_entries[i])
        if(str_contains_commas(time_value) or str_contains_commas(mem_value)):
            multiattempt_processes.add(sname)
    return multiattempt_processes

##################################################
def extract_processdeps_info(entries_lineno,process_entries):
    processdeps_map={}
    processdeps_sep={}
    deps_syntax_ok=True
    for i in range(len(process_entries)):
        fields=process_entries[i].split()
        sname=extract_process_name(process_entries[i])
        dep_syntax_ok,separator,deps=extract_process_deps(entries_lineno[i],process_entries[i])
        if(not dep_syntax_ok):
            deps_syntax_ok=False
        processdeps_sep[sname]=separator
        processdeps_map[sname]=deps
    return deps_syntax_ok,processdeps_sep,processdeps_map

##################################################
def processnames_duplicated(entries_lineno,process_entries):
    processnames=set()
    lineno=1
    for i in range(len(process_entries)):
        sname=extract_process_name(process_entries[i])
        if sname in processnames:
            print("Error: process",sname,"in line",entries_lineno[i],"is duplicated", file=sys.stderr)
            return True
        else:
            processnames.add(sname)
        lineno=lineno+1
    return False

##################################################
def depnames_correct(processdeps_map):
    processnames=set()
    processdepnames=set()

    # Obtain sets of process names and names of process dependencies
    for processname in processdeps_map:
        processnames.add(processname)
        for elem in processdeps_map[processname]:
            processdepnames.add(elem.processname)

    for name in processdepnames:
        if name not in processnames:
            print("Error: unrecognized process dependency",name, file=sys.stderr)
            return False

    return True

##################################################
def processname_can_be_added(sname,processed_processes,processdeps_map):
    # Check if process name has already been added
    if sname in processed_processes:
        return False

    # Check if all dependencies for process name were processed
    for elem in processdeps_map[sname]:
        if(elem.processname not in processed_processes):
            return False

    return True

##################################################
def order_process_entries(process_entries,processdeps_map,ordered_process_entries):
    processed_processes=set()
    # Add processes to ordered processes list incrementally
    while len(processed_processes)!=len(processdeps_map):
        prev_proc_processes_len=len(processed_processes)
        # Explore list of process entries
        for entry in process_entries:
            sname=extract_process_name(entry)
            if(processname_can_be_added(sname,processed_processes,processdeps_map)):
                processed_processes.add(sname)
                ordered_process_entries.append(entry)
        # Check if no processes were added
        if(prev_proc_processes_len==len(processed_processes)):
            print("Error: the analysis file contains at least one cycle", file=sys.stderr)
            return ordered_process_entries

    return ordered_process_entries

##################################################
def after_dep_has_multatt_process(entries_lineno,multiattempt_processes,processdeps_map):
    found=False
    for sname in processdeps_map:
        deplist=processdeps_map[sname]
        i=0
        while i<len(deplist) and not found:
            if(deplist[i].deptype=="after" and deplist[i].processname in multiattempt_processes):
                found=True
                print("Error:",sname,"process has an 'after' dependency with a multiple-attempt process (",deplist[i].processname,")", file=sys.stderr)
            else:
                i=i+1
    if(found):
        return True
    else:
        return False

##################################################
def processdeps_correct(entries_lineno,process_entries,multiattempt_processes,processdeps_map,ordered_process_entries):

    # Check existence of duplicated processes
    if(processnames_duplicated(entries_lineno,process_entries)):
        return False

    # Check dependency names
    if(not depnames_correct(processdeps_map)):
        return False

    # Check "after" dependency type is not used over a multi-attempt process
    if(after_dep_has_multatt_process(entries_lineno,multiattempt_processes,processdeps_map)):
        return False
    # Reorder process entries
    order_process_entries(process_entries,processdeps_map,ordered_process_entries)
    if(len(process_entries)!=len(ordered_process_entries)):
        return False

    return True

##################################################
def print_entries(config_entries,process_entries):
    for e in config_entries:
        print(e)
    for e in process_entries:
        print(e)

##################################################
def get_graph_linestyle(separator):
    if separator=="?":
        return "dashed"
    elif separator==",":
        return "solid"
    elif separator=="":
        return "solid"

##################################################
def print_graph(ordered_process_entries,processdeps_sep,processdeps_map):
    # Print header
    print("digraph G {")
    print("overlap=false;")
    print("splines=true;")
    print("K=1;")

    # Set representation for processes
    print("node [shape = ellipse];")

    # Process processes
    for process in processdeps_map:
        line_style=get_graph_linestyle(processdeps_sep[process])
        if len(processdeps_map[process])==0:
            print("start","->",process, "[ label= \"\" ,","color = black ];")
        else:
            for elem in processdeps_map[process]:
                print('"'+elem.processname+'"',"->",process, "[ label= \""+elem.deptype+"\" ,","style=",line_style,", color = black ];")

    # Print footer
    print("}")

##################################################
def extract_all_deps_for_process(sname,processdeps_map,result):
    if sname in processdeps_map:
        for processdep in processdeps_map[sname]:
            result.add(processdep.processname)
            extract_all_deps_for_process(processdep.processname,processdeps_map,result)

##################################################
def print_deps(ordered_process_entries,processdeps_map):
    for entry in ordered_process_entries:
        # Extract dependencies for process
        sname=extract_process_name(entry)
        processdeps=set()
        extract_all_deps_for_process(sname,processdeps_map,processdeps)

        # Print dependencies for process
        depstr=""
        for dep in processdeps:
            if(depstr==""):
                depstr=dep
            else:
                depstr=depstr+" "+dep
        print(sname,":",depstr)

##################################################
def sname_valid(sname):
    for c in sname:
        if not(c.isalpha() or c.isdigit() or c=="_"):
            return 0
    return 1

##################################################
def snames_valid(processdeps_map):
    for sname in processdeps_map:
        if(not sname_valid(sname)):
            print("Error: process name",sname,"contains not allowed characters (only letters, numbers and underscores are allowed)", file=sys.stderr)
            return 0
    return 1

##################################################
def process_pars(flags,values):
    config_entries=extract_config_entries(values["pfile"])
    entries_lineno,process_entries=extract_process_entries(values["pfile"])
    multiattempt_processes=extract_processes_with_multiattempt(process_entries)
    deps_syntax_ok,processdeps_sep,processdeps_map=extract_processdeps_info(entries_lineno,process_entries)
    if(not deps_syntax_ok):
       print("Process dependencies are not syntactically correct", file=sys.stderr)
       return 1
    if(not snames_valid(processdeps_map)):
       print("Process names are not valid", file=sys.stderr)
       return 1
    ordered_process_entries=[]
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
    (flags,values)=take_pars()

    # check parameters
    check_pars(flags,values)

    # process parameters
    success=process_pars(flags,values)

    exit(success)

if __name__ == "__main__":
    main(sys.argv)
