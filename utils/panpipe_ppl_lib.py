# *- python -*

# import modules
import io
import sys

# Constants
NONE_PROCESS_DEP = "none"
PROCSPEC_FEXT = "procspec"
PPLOPTS_FEXT = "opts"

##################################################
class DirectedGraph:
    def __init__(self):
        self.graph = {}

    def add_vertex(self, vertex):
        if vertex not in self.graph:
            self.graph[vertex] = []

    def add_edge(self, from_vertex, to_vertex):
        if from_vertex in self.graph and to_vertex in self.graph:
            if to_vertex not in self.graph[from_vertex]:
                self.graph[from_vertex].append(to_vertex)

    def get_neighbors(self, vertex):
        if vertex in self.graph:
            return self.graph[vertex]
        else:
            return []

    def get_num_vertices(self):
        return len(self.graph())

    def get_num_edges(self):
        result = 0
        for vertex in self.graph:
            result += len(self.graph[vertex])
        return result

    def __str__(self):
        result = ""
        for vertex in self.graph:
            neighbors = ", ".join(self.graph[vertex])
            result += f"{vertex} -> [{neighbors}]\n"
        return result

##################################################
class processdep_data:
    def __init__(self):
        self.deptype = None
        self.processname = None

##################################################
def get_procspec_fname(prefix):
    return prefix + "." + PROCSPEC_FEXT

##################################################
def entry_is_comment(entry):
    fields=entry.split()
    if len(fields) == 0:
        return False
    elif fields[0][0] == "#":
        return True
    else:
        return False

##################################################
def entry_is_empty(entry):
    fields=entry.split()
    if len(fields) == 0:
        return True
    else:
        return False

##################################################
def extract_process_name(entry):
    fields=entry.split()
    if len(fields) == 0:
        return ""
    else:
        return fields[0]

##################################################
def get_dep_separator(pdeps_str):
    if ',' in pdeps_str and '?' in pdeps_str:
        return True, ',?'
    elif ',' in pdeps_str:
        return False, ','
    elif '?' in pdeps_str:
        return False, '?'
    else:
        return False, ''

##################################################
def extract_process_deps(entry_lineno, entry):
    deps_syntax_ok = True
    # extract text field
    fields = entry.split()
    pdeps_str = ""
    for f in fields:
        if f.find("processdeps=")==0:
            pdeps_str=f[len("processdeps="):]

    # Return empty list of process dependencies if corresponding field was
    # not found
    if len(pdeps_str)==0:
        return deps_syntax_ok, []

    # Check that dependency separators (, and ?) are not mixed
    seps_mixed, separator=get_dep_separator(pdeps_str)
    if seps_mixed:
        deps_syntax_ok=False
        print("Error: dependency separators mixed in process dependency (", pdeps_str, ") at line number", entry_lineno, file=sys.stderr)
        return deps_syntax_ok,[]

    # create list of process dependencies
    pdeps_list=[]
    if(separator == ''):
        pdeps_fields=[pdeps_str]
    else:
        pdeps_fields=pdeps_str.split(separator)
    for pdep in pdeps_fields:
        if pdep!=NONE_PROCESS_DEP:
            pdep_fields=pdep.split(":")
            if(len(pdep_fields) == 2 and pdep_fields[1] != ''):
                data=processdep_data()
                data.deptype=pdep_fields[0]
                data.processname=pdep_fields[1]
                pdeps_list.append(data)
            else:
                deps_syntax_ok=False
                print("Error: incorrect definition of process dependency (", pdeps_str, ") at line number", entry_lineno, file=sys.stderr)

    return deps_syntax_ok,separator,pdeps_list

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
        prname=extract_process_name(process_entries[i])
        time_value=extract_time_value(process_entries[i])
        mem_value=extract_mem_value(process_entries[i])
        if(str_contains_commas(time_value) or str_contains_commas(mem_value)):
            multiattempt_processes.add(prname)
    return multiattempt_processes

##################################################
def extract_processdeps_info(entries_lineno,process_entries):
    processdeps_map = {}
    processdeps_sep = {}
    deps_syntax_ok = True
    for i in range(len(process_entries)):
        fields = process_entries[i].split()
        prname = extract_process_name(process_entries[i])
        dep_syntax_ok, separator, deps = extract_process_deps(entries_lineno[i], process_entries[i])
        if(not dep_syntax_ok):
            deps_syntax_ok=False
        processdeps_sep[prname] = separator
        processdeps_map[prname] = deps
    return deps_syntax_ok, processdeps_sep, processdeps_map

##################################################
def processnames_duplicated(entries_lineno, process_entries):
    processnames=set()
    lineno=1
    for i in range(len(process_entries)):
        prname=extract_process_name(process_entries[i])
        if prname in processnames:
            print("Error: process", prname, "in line", entries_lineno[i], "is duplicated", file=sys.stderr)
            return True
        else:
            processnames.add(prname)
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
            print("Error: unrecognized process dependency", name, file=sys.stderr)
            return False

    return True

##################################################
def processname_can_be_added(prname, processed_processes, processdeps_map):
    # Check if process name has already been added
    if prname in processed_processes:
        return False

    # Check if all dependencies for process name were processed
    for elem in processdeps_map[prname]:
        if(elem.processname not in processed_processes):
            return False

    return True

##################################################
def order_process_entries(process_entries, processdeps_map, ordered_process_entries):
    processed_processes=set()
    # Add processes to ordered processes list incrementally
    while len(processed_processes)!=len(processdeps_map):
        prev_proc_processes_len=len(processed_processes)
        # Explore list of process entries
        for entry in process_entries:
            prname=extract_process_name(entry)
            if(processname_can_be_added(prname, processed_processes, processdeps_map)):
                processed_processes.add(prname)
                ordered_process_entries.append(entry)
        # Check if no processes were added
        if(prev_proc_processes_len==len(processed_processes)):
            print("Error: the analysis file contains at least one cycle", file=sys.stderr)
            return ordered_process_entries

    return ordered_process_entries

##################################################
def after_dep_has_multatt_process(entries_lineno, multiattempt_processes, processdeps_map):
    found=False
    for prname in processdeps_map:
        deplist=processdeps_map[prname]
        i=0
        while i<len(deplist) and not found:
            if(deplist[i].deptype=="after" and deplist[i].processname in multiattempt_processes):
                found=True
                print("Error:", prname, "process has an 'after' dependency with a multiple-attempt process (", deplist[i].processname,")", file=sys.stderr)
            else:
                i=i+1
    if(found):
        return True
    else:
        return False

##################################################
def processdeps_correct(entries_lineno, process_entries, multiattempt_processes, processdeps_map, ordered_process_entries):

    # Check existence of duplicated processes
    if(processnames_duplicated(entries_lineno, process_entries)):
        return False

    # Check dependency names
    if(not depnames_correct(processdeps_map)):
        return False

    # Check "after" dependency type is not used over a multi-attempt process
    if(after_dep_has_multatt_process(entries_lineno, multiattempt_processes, processdeps_map)):
        return False
    # Reorder process entries
    order_process_entries(process_entries, processdeps_map, ordered_process_entries)
    if(len(process_entries)!=len(ordered_process_entries)):
        return False

    return True

##################################################
def print_entries(process_entries):
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
def print_graph(ordered_process_entries, processdeps_sep, processdeps_map):
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
            print("start", "->", process, "[ label= \"\" ,", "color = black ];")
        else:
            for elem in processdeps_map[process]:
                print('"'+elem.processname+'"', "->", process, "[ label= \""+elem.deptype+"\" ,","style=", line_style, ", color = black ];")

    # Print footer
    print("}")

##################################################
def extract_all_deps_for_process(prname, processdeps_map, result):
    if prname in processdeps_map:
        for processdep in processdeps_map[prname]:
            result.add(processdep.processname)
            extract_all_deps_for_process(processdep.processname, processdeps_map, result)

##################################################
def print_deps(ordered_process_entries, processdeps_map):
    for entry in ordered_process_entries:
        # Extract dependencies for process
        prname=extract_process_name(entry)
        processdeps=set()
        extract_all_deps_for_process(prname, processdeps_map, processdeps)

        # Print dependencies for process
        depstr = ""
        for dep in processdeps:
            if(depstr==""):
                depstr = dep
            else:
                depstr = depstr+" "+dep
        print(prname, ":", depstr)

##################################################
def prname_valid(prname):
    for c in prname:
        if not(c.isalpha() or c.isdigit() or c=="_"):
            return 0
    return 1

##################################################
def prnames_valid(processdeps_map):
    for prname in processdeps_map:
        if(not prname_valid(prname)):
            print("Error: process name", prname, "contains not allowed characters (only letters, numbers and underscores are allowed)", file=sys.stderr)
            return 0
    return 1
