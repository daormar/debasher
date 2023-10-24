# *- python -*

# import modules
import io
import sys
import re
import os

# Constants
NONE_PROCESS_DEP = "none"
PROCSPEC_FEXT = "procspec"
PPLOPTS_FEXT = "opts"
PPLOPTS_EXHAUSTIVE_FEXT = "opts_exh"
FIFOS_FEXT = "fifos"
ARG_SEP = "<_ARG_SEP_>"
ASSOC_ARRAY_ELEM_SEP = "__ELEMSEP__"
ASSOC_ARRAY_KEY_LEN = "__LEN__"
PROCESS_TASKIDX_SEP = "__PROCESS_TASKIDX_SEP__"
OPT_PROCESS_SEP = "__OPT_PROCESS_SEP__"
OPTPROC_HUB_SUFFIX = "__OPTPROC_HUB_SUFFIX"

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
class DependencyGraph:
    def __init__(self, ppl_files_pref):
        self.procspec_file = self.get_procspec_fname(ppl_files_pref)
        self.entries_lineno, self.process_entries = self.extract_process_entries(self.procspec_file)
        self.multiattempt_processes = self.extract_processes_with_multiattempt(self.process_entries)
        self.deps_syntax_ok, self.processdeps_sep, self.processdeps_map = self.extract_processdeps_info(self.entries_lineno, self.process_entries)

    def get_dep_info(self):
        dep_info = {}
        for entry in self.process_entries:
            # Extract dependencies for process
            prname = self.extract_process_name(entry)
            processdeps = set()
            self.extract_all_deps_for_process(prname, processdeps)
            # Add dependencies to dictionary
            deplist = []
            for process in processdeps:
                deplist.append(process)
            dep_info[prname] = deplist
        return dep_info

    def get_procspec_fname(self, prefix):
        return prefix + "." + PROCSPEC_FEXT

    def extract_process_entries(self, procspec_file):
        entries_lineno = []
        process_entries = []
        file = open(self.procspec_file, 'r')
        # read file entry by entry
        lineno = 1
        for entry in file:
            entry = entry.strip("\n")
            if not self.entry_is_comment(entry) and not self.entry_is_empty(entry):
                process_entries.append(entry)
                entries_lineno.append(lineno)
            lineno=lineno+1

        return entries_lineno, process_entries

    def entry_is_comment(self, entry):
        fields = entry.split()
        if len(fields) == 0:
            return False
        elif fields[0][0] == "#":
            return True
        else:
            return False

    def entry_is_empty(self, entry):
        fields = entry.split()
        if len(fields) == 0:
            return True
        else:
            return False

    def extract_processes_with_multiattempt(self, process_entries):
        multiattempt_processes = set()
        for i in range(len(process_entries)):
            prname = self.extract_process_name(process_entries[i])
            time_value = self.extract_time_value(process_entries[i])
            mem_value = self.extract_mem_value(process_entries[i])
            if(self.str_contains_commas(time_value) or self.str_contains_commas(mem_value)):
                multiattempt_processes.add(prname)
        return multiattempt_processes

    def str_contains_commas(self, str):
        if(',' in str):
            return True
        else:
            return False

    def extract_time_value(self, entry):
        fields = entry.split()
        i = 0
        found = False
        value = ""
        while i<len(fields) and not found:
            if fields[i].find("time=") == 0:
                found = True
                value = fields[i][5:]
            else:
                i = i+1
        return value

    def extract_mem_value(self, entry):
        fields = entry.split()
        i = 0
        found = False
        value = ""
        while i<len(fields) and not found:
            if fields[i].find("mem=") == 0:
                found = True
                value = fields[i][4:]
            else:
                i = i+1
        return value

    def extract_processdeps_info(self, entries_lineno, process_entries):
        processdeps_map = {}
        processdeps_sep = {}
        deps_syntax_ok = True
        for i in range(len(process_entries)):
            fields = process_entries[i].split()
            prname = self.extract_process_name(process_entries[i])
            dep_syntax_ok, separator, deps = self.extract_process_deps(entries_lineno[i], process_entries[i])
            if(not dep_syntax_ok):
                deps_syntax_ok=False
            processdeps_sep[prname] = separator
            processdeps_map[prname] = deps
        return deps_syntax_ok, processdeps_sep, processdeps_map

    def extract_process_deps(self, entry_lineno, entry):
        deps_syntax_ok = True
        # extract text field
        fields = entry.split()
        pdeps_str = ""
        for f in fields:
            if f.find("processdeps=") == 0:
                pdeps_str = f[len("processdeps="):]

        # Return empty list of process dependencies if corresponding field was
        # not found
        if len(pdeps_str)==0:
            return deps_syntax_ok, []

        # Check that dependency separators (, and ?) are not mixed
        seps_mixed, separator = self.get_dep_separator(pdeps_str)
        if seps_mixed:
            deps_syntax_ok = False
            print("Error: dependency separators mixed in process dependency (", pdeps_str, ") at line number", entry_lineno, file=sys.stderr)
            return deps_syntax_ok, []

        # create list of process dependencies
        pdeps_list=[]
        if(separator == ''):
            pdeps_fields = [pdeps_str]
        else:
            pdeps_fields = pdeps_str.split(separator)
        for pdep in pdeps_fields:
            if pdep != NONE_PROCESS_DEP:
                pdep_fields = pdep.split(":")
                if(len(pdep_fields) == 2 and pdep_fields[1] != ''):
                    data = processdep_data()
                    data.deptype = pdep_fields[0]
                    data.processname = pdep_fields[1]
                    pdeps_list.append(data)
                else:
                    deps_syntax_ok=False
                    print("Error: incorrect definition of process dependency (", pdeps_str, ") at line number", entry_lineno, file=sys.stderr)

        return deps_syntax_ok,separator,pdeps_list

    def get_dep_separator(self, pdeps_str):
        if ',' in pdeps_str and '?' in pdeps_str:
            return True, ',?'
        elif ',' in pdeps_str:
            return False, ','
        elif '?' in pdeps_str:
            return False, '?'
        else:
            return False, ''

    def syntax_ok(self):
        return self.syntax_ok

    def prname_valid(self, prname):
        for c in prname:
            if not(c.isalpha() or c.isdigit() or c=="_"):
                return 0
        return 1

    def prnames_valid(self):
        for prname in self.processdeps_map:
            if(not self.prname_valid(prname)):
                print("Error: process name", prname, "contains not allowed characters (only letters, numbers and underscores are allowed)", file=sys.stderr)
                return 0
        return 1

    def processdeps_correct(self, ordered_process_entries):

        # Check existence of duplicated processes
        if(self.processnames_duplicated()):
            return False

        # Check dependency names
        if(not self.depnames_correct()):
            return False

        # Check "after" dependency type is not used over a multi-attempt process
        if(self.after_dep_has_multatt_process()):
            return False

        # Reorder process entries
        self.order_process_entries(ordered_process_entries)
        if(len(self.process_entries) != len(ordered_process_entries)):
            return False

        return True

    def processnames_duplicated(self):
        processnames=set()
        lineno=1
        for i in range(len(self.process_entries)):
            prname = self.extract_process_name(self.process_entries[i])
            if prname in processnames:
                print("Error: process", prname, "in line", entries_lineno[i], "is duplicated", file=sys.stderr)
                return True
            else:
                processnames.add(prname)
            lineno=lineno+1
        return False

    def extract_process_name(self, entry):
        fields=entry.split()
        if len(fields) == 0:
            return ""
        else:
            return fields[0]

    def depnames_correct(self):
        processnames=set()
        processdepnames=set()

        # Obtain sets of process names and names of process dependencies
        for processname in self.processdeps_map:
            processnames.add(processname)
            for elem in self.processdeps_map[processname]:
                processdepnames.add(elem.processname)

        for name in processdepnames:
            if name not in processnames:
                print("Error: unrecognized process dependency", name, file=sys.stderr)
                return False

        return True

    def after_dep_has_multatt_process(self):
        found = False
        for prname in self.processdeps_map:
            deplist = self.processdeps_map[prname]
            i = 0
            while i<len(deplist) and not found:
                if(deplist[i].deptype=="after" and deplist[i].processname in self.multiattempt_processes):
                    found = True
                    print("Error:", prname, "process has an 'after' dependency with a multiple-attempt process (", deplist[i].processname,")", file=sys.stderr)
                else:
                    i = i+1
        if(found):
            return True
        else:
            return False

    def order_process_entries(self, ordered_process_entries):
        processed_processes=set()
        # Add processes to ordered processes list incrementally
        while len(processed_processes) != len(self.processdeps_map):
            prev_proc_processes_len=len(processed_processes)
            # Explore list of process entries
            for entry in self.process_entries:
                prname = self.extract_process_name(entry)
                if self.processname_can_be_added(prname, processed_processes):
                    processed_processes.add(prname)
                    ordered_process_entries.append(entry)
            # Check if no processes were added
            if(prev_proc_processes_len==len(processed_processes)):
                print("Error: the analysis file contains at least one cycle", file=sys.stderr)
                return ordered_process_entries

        return ordered_process_entries

    def processname_can_be_added(self, prname, processed_processes):
        # Check if process name has already been added
        if prname in processed_processes:
            return False

        # Check if all dependencies for process name were processed
        for elem in self.processdeps_map[prname]:
            if(elem.processname not in processed_processes):
                return False

        return True

    def get_graph_linestyle(self, separator):
        if separator=="?":
            return "dashed"
        elif separator==",":
            return "solid"
        elif separator=="":
            return "solid"

    def print(self):
        # Print header
        print("digraph G {")
        print("overlap=false;")
        print("splines=true;")
        print("K=1;")

        # Set representation for processes
        print("node [shape = box];")

        # Process processes
        for process in self.processdeps_map:
            line_style = self.get_graph_linestyle(self.processdeps_sep[process])
            if len(self.processdeps_map[process]) == 0:
                print("start", "->", process, "[ label= \"\" ,", "color = black ];")
            else:
                for elem in self.processdeps_map[process]:
                    print('"'+elem.processname+'"', "->", process, "[ label= \""+elem.deptype+"\" ,","style=", line_style, ", color = black ];")

        # Print footer
        print("}")

    def print_deps(self, ordered_process_entries):
        for entry in ordered_process_entries:
            # Extract dependencies for process
            prname = self.extract_process_name(entry)
            processdeps = set()
            self.extract_all_deps_for_process(prname, processdeps)

            # Print dependencies for process
            depstr = ""
            for dep in processdeps:
                if(depstr==""):
                    depstr = dep
                else:
                    depstr = depstr+" "+dep
            print(prname, ":", depstr)

    def extract_all_deps_for_process(self, prname, result):
        if prname in self.processdeps_map:
            for processdep in self.processdeps_map[prname]:
                result.add(processdep.processname)
                self.extract_all_deps_for_process(processdep.processname, result)

##################################################
class ProcessGraph:
    def __init__(self, ppl_files_pref):
        self.pplopts_exhaustive_file = self.get_pplopts_exh_fname(ppl_files_pref)
        self.pplopts_exh = self.load_pplopt_exh(self.pplopts_exhaustive_file)
        self.process_out_values = self.get_process_out_values(self.pplopts_exh)
        self.fifos_file = self.get_fifos_fname(ppl_files_pref)
        self.fifo_owners, self.fifo_users, self.fifo_deps = self.load_fifos(self.fifos_file)

    def get_pplopts_exh_fname(self, prefix):
        return prefix + "." + PPLOPTS_EXHAUSTIVE_FEXT

    def load_pplopt_exh(self, pplopt_exh_fname):
        pplopts_exh = {}
        file = open(pplopt_exh_fname, 'r')
        # read file entry by entry
        for entry in file:
            # Extract entry information
            words = entry.split()
            process_info = words[0]
            process_opts = "".join(words[2:])

            # Extract elements of process info
            process_info_elems = self.get_process_taskidx_elems_ppl_file(process_info)
            if len(process_info_elems) == 2:
                processname = process_info_elems[0]
                # Continue processing if the entry is not providing the
                # number of tasks
                if process_info_elems[1] != ASSOC_ARRAY_KEY_LEN:
                    task_idx = int(process_info_elems[1])
                    # Make room for options
                    if processname not in pplopts_exh:
                        pplopts_exh[processname] = []
                    while len(pplopts_exh[processname]) <= task_idx:
                        pplopts_exh[processname].append([])
                    # Create list from process options
                    opt_list = self.get_opt_list_ppl_file(process_opts)
                    pplopts_exh[processname][task_idx] = opt_list

        return pplopts_exh

    def get_opt_list_ppl_file(self, process_opts):
        return re.split(re.escape(ARG_SEP), process_opts)

    def get_process_taskidx_elems_ppl_file(self, process_info):
        return re.split(re.escape(ASSOC_ARRAY_ELEM_SEP), process_info)

    def get_process_out_values(self, pplopts_exh):
        process_out_values = {}
        for process, opts_list in pplopts_exh.items():
            for task_idx in range(len(opts_list)):
                opts = opts_list[task_idx]
                i = 0
                while i < len(opts):
                    if os.path.isabs(opts[i]):
                        if i > 0 and self.str_is_output_option(opts[i-1]):
                            if opts[i] in process_out_values:
                                process_out_values[opts[i]].append((process, task_idx, opts[i-1]))
                            else:
                                process_out_values[opts[i]] = [(process, task_idx, opts[i-1])]
                    i += 1
        return process_out_values

    def get_fifos_fname(self, prefix):
        return prefix + "." + FIFOS_FEXT

    def load_fifos(self, fifos_fname):
        fifo_owners = {}
        fifo_users = {}
        fifo_deps = {}

        file = open(fifos_fname, 'r')
        # read file entry by entry
        for entry in file:
            # Extract entry information
            words = entry.split()
            augm_fifoname = words[0]
            fifo_owner_elems = self.get_process_taskidx_elems_ppl_file(words[1])
            fifo_owner = fifo_owner_elems[0]
            fifo_owner_taskidx = fifo_owner_elems[1]
            fifodep = words[2]
            fifo_user_elems = self.get_process_taskidx_elems_ppl_file(words[3])
            fifo_user = fifo_user_elems[0]
            fifo_user_taskidx = fifo_user_elems[1]

            # Populate dictionaries
            fifo_owners[augm_fifoname] = fifo_owner, fifo_owner_taskidx
            fifo_users[augm_fifoname] = fifo_user, fifo_user_taskidx
            fifo_deps[augm_fifoname] = fifodep

        return fifo_owners, fifo_users, fifo_deps

    def print(self):
        # Print header
        print("digraph G {")
        print("overlap=false;")

        print("splines=true;")
        print("K=1;")

        # Extract information
        process_graph_repres = self.gen_process_graph_repres()
        opt_to_processes = self.get_opt_to_processes()
        optproc_to_arrsize = self.gen_optproc_to_arrsize(opt_to_processes)
        opt_repres = self.gen_opt_graph_repres(opt_to_processes, optproc_to_arrsize)
        opt_hub_repres = self.gen_opt_hub_graph_repres(optproc_to_arrsize)

        # Set representation for processes and options
        print("node [shape = box];", "; ".join(process_graph_repres))
        print("node [shape = ellipse];", "; ".join(opt_repres))
        print("node [shape = point];", "; ".join(opt_hub_repres))

        # Add process graph arcs
        self.print_proc_graph_arcs(opt_to_processes, optproc_to_arrsize)

        print("}")

    def gen_process_graph_repres(self):
        process_graph_repres = []
        for process in self.pplopts_exh:
            process_graph_repres.append(process)
        return process_graph_repres

    def get_opt_to_processes(self):
        opt_to_processes = {}
        for process, opts_list in self.pplopts_exh.items():
            for task_idx in range(len(opts_list)):
                opts = opts_list[task_idx]
                for i in range(len(opts)):
                    elem = opts[i]
                    if i+1 < len(opts) and not self.str_is_option(opts[i+1]):
                        value = opts[i+1]
                    else:
                        value = None
                    if self.str_is_option(elem):
                        if elem in opt_to_processes:
                            opt_to_processes[elem].append((self.get_process_taskidx_string(process, task_idx), value))
                        else:
                            opt_to_processes[elem] = [(self.get_process_taskidx_string(process, task_idx), value)]
        return opt_to_processes

    def str_is_option(self, string):
        if string[0] == "-" or string[0:2] == "--":
            return True
        else:
            return False

    def str_is_output_option(self, string):
        if string[0:4] == "-out" or string[0:5] == "--out":
            return True
        else:
            return False

    def get_process_taskidx_string(self, processname, task_idx):
        return processname + PROCESS_TASKIDX_SEP + str(task_idx)

    def get_process_taskidx_elems(self, process_info):
        return re.split(re.escape(PROCESS_TASKIDX_SEP), process_info)

    def gen_optproc_to_arrsize(self, opt_to_processes):
        optproc_to_arrsize = {}
        # Iterate over options
        for opt in opt_to_processes:
            # Iterate over option data
            for opt_data in opt_to_processes[opt]:
                # Extract data
                process_info = opt_data[0]
                process_info_elems = self.get_process_taskidx_elems(process_info)
                processname = process_info_elems[0]
                task_idx = process_info_elems[1]

                # Fill array size information for option and process
                if (opt, processname) in optproc_to_arrsize:
                    optproc_to_arrsize[(opt, processname)] += 1
                else:
                    optproc_to_arrsize[(opt, processname)] = 1

        return optproc_to_arrsize

    def gen_opt_graph_repres(self, opt_to_processes, optproc_to_arrsize):
        opt_repres = []
        # Iterate over options
        for opt in opt_to_processes:
            taskidx_to_processes = {}
            processes = {}

            # Iterate over processes related to opt
            for opt_procs in opt_to_processes[opt]:
                # Extract data
                process_info = opt_procs[0]
                process_info_elems = self.get_process_taskidx_elems(process_info)
                processname = process_info_elems[0]
                task_idx = process_info_elems[1]

                # Fill process information organized by task index (only for
                # task arrays)
                if optproc_to_arrsize[(opt, processname)] == 1:
                    if processname not in processes:
                        processes[process_info] = 1
                else:
                    if task_idx in taskidx_to_processes:
                        taskidx_to_processes[task_idx].append(process_info)
                    else:
                        taskidx_to_processes[task_idx] = [process_info]

            # Generate representation
            if processes:
                graph_elem = self.gen_opt_graph_elem(opt, "", processes)
                opt_repres.append(graph_elem)
            for task_idx in taskidx_to_processes:
                graph_elem = self.gen_opt_graph_elem(opt, str(task_idx), taskidx_to_processes[task_idx])
                opt_repres.append(graph_elem)

        return opt_repres

    def gen_opt_graph_elem(self, opt, suffix, proc_iterable):
        graph_elem = '{node [label="' + opt + suffix + '"] '
        for process_info in proc_iterable:
            opt_graph = self.get_opt_graph(opt, process_info)
            graph_elem += '"' + opt_graph + '"; '
        graph_elem += "}"
        return graph_elem

    def get_opt_graph(self, opt, process_info):
        return opt + OPT_PROCESS_SEP + process_info

    def get_opt_hub_graph(self, optproc):
        return self.get_opt_graph(optproc[0], optproc[1]) + OPTPROC_HUB_SUFFIX

    def gen_opt_hub_graph_repres(self, optproc_to_arrsize):
        opt_hub_graph_repres = []
        for optproc in optproc_to_arrsize:
            if optproc_to_arrsize[optproc] > 1:
                opt_hub_graph = self.get_opt_hub_graph(optproc)
                opt_hub_graph_repres.append('"' + opt_hub_graph + '"')
        return opt_hub_graph_repres

    def print_proc_graph_arcs(self, opt_to_processes, optproc_to_arrsize):
        # Iterate over options
        for opt in opt_to_processes:
            # Iterate over processes related to opt
            for opt_procs in opt_to_processes[opt]:
                self.print_opt_to_proc_arcs(optproc_to_arrsize, opt, opt_procs)
                self.print_opt_to_opt_arcs(optproc_to_arrsize, opt, opt_procs)

    def print_opt_to_proc_arcs(self, optproc_to_arrsize, opt, opt_procs):
        # Extract process information
        process_info = opt_procs[0]
        process_info_elems = self.get_process_taskidx_elems(process_info)
        processname = process_info_elems[0]
        opt_val = opt_procs[1]

        # Print arcs
        if optproc_to_arrsize[(opt, processname)] == 1:
            self.print_opt_to_proc_args_noarr(process_info, opt, opt_val)
        else:
            self.print_opt_to_proc_args_arr(process_info, opt, opt_val)

    def print_opt_to_proc_args_noarr(self, process_info, opt, opt_val):
        # Initialize variables
        process_info_elems = self.get_process_taskidx_elems(process_info)
        processname = process_info_elems[0]
        opt_graph = self.get_opt_graph(opt, process_info)

        # Print arc
        if self.str_is_output_option(opt):
            print(processname, "->", '"'+ opt_graph +'"', ";")
        elif self.process_is_fifo_owner(process_info, opt_val):
            print(processname, "->", '"'+ opt_graph +'"', "[ dir=none ] ;")
        elif self.process_is_fifo_user(process_info, opt_val):
            print('"'+ opt_graph +'"', "->", processname, "[ dir=none ] ;")
        else:
            print('"'+ opt_graph +'"', "->", processname, ";")

    def print_opt_to_proc_args_arr(self, process_info, opt, opt_val):
        # Initialize variables
        process_info_elems = self.get_process_taskidx_elems(process_info)
        processname = process_info_elems[0]
        task_idx = int(process_info_elems[1])
        opt_graph = self.get_opt_graph(opt, process_info)

        # Get name of option hub
        opt_hub = self.get_opt_hub_graph((opt, processname))

        # Print arc
        if self.str_is_output_option(opt):
            if task_idx == 0:
                print(processname, "->", '"'+ opt_hub +'"', ";")
            print('"'+ opt_hub +'"', "->", '"'+ opt_graph +'"', ";")
        elif self.process_is_fifo_owner(process_info, opt_val):
            if task_idx == 0:
                print(processname, "->", '"'+ opt_hub +'"', "[ dir=none ] ;")
            print('"'+ opt_hub +'"', "->", '"'+ opt_graph +'"', "[ dir=none ] ;")
        elif self.process_is_fifo_user(process_info, opt_val):
            print('"'+ opt_graph +'"', "->", '"'+ opt_hub +'"', "[ dir=none ] ;")
            if task_idx == 0:
                print('"'+ opt_hub +'"', "->", processname, "[ dir=none ] ;")
        else:
            print('"'+ opt_graph +'"', "->", '"'+ opt_hub +'"', ";")
            if task_idx == 0:
                print('"'+ opt_hub +'"', "->", processname, ";")

    def get_augm_fifoname(self, abs_fifoname):
        basename = os.path.basename(abs_fifoname)
        dirname = os.path.dirname(abs_fifoname)
        return os.path.basename(dirname) + "/" + basename

    def process_is_fifo_owner(self, process_info, abs_fifoname):
        if not os.path.isabs(abs_fifoname):
            return False
        else:
            base_fname = self.get_augm_fifoname(abs_fifoname)
            if base_fname in self.fifo_owners:
                if process_info == self.get_process_taskidx_string(*self.fifo_owners[base_fname]):
                    return True
                else:
                    return False
            else:
                return False

    def process_is_fifo_user(self, process_info, abs_fifoname):
        if not os.path.isabs(abs_fifoname):
            return False
        else:
            base_fname = self.get_augm_fifoname(abs_fifoname)
            if base_fname in self.fifo_users:
                if process_info == self.get_process_taskidx_string(*self.fifo_users[base_fname]):
                    return True
                else:
                    return False
            else:
                return False

    def print_opt_to_opt_arcs(self, optproc_to_arrsize, opt, opt_procs):
        # Extract process information
        process_info = opt_procs[0]

        # Get option value
        opt_val = opt_procs[1]

        # Print arcs if required
        if not self.str_is_output_option(opt) and os.path.isabs(opt_val):
            if opt_val in self.process_out_values:
                self.print_opt_to_opt_outval(process_info, opt, opt_val)
            else:
                if self.process_is_fifo_owner(process_info, opt_val):
                    self.print_opt_to_opt_fifo(process_info, opt, opt_val)

    def print_opt_to_opt_fifo(self, process_info, opt, opt_val):
        # Obtain origin node
        base_fname = self.get_augm_fifoname(opt_val)
        orig_process_info = self.get_process_taskidx_string(*self.fifo_owners[base_fname])
        orig_opt = self.get_fifo_opt(orig_process_info, opt_val)
        orig_opt_graph = self.get_opt_graph(orig_opt, orig_process_info)

        # Obtain destination node
        dest_process_info = self.get_process_taskidx_string(*self.fifo_users[base_fname])
        dest_opt = self.get_fifo_opt(dest_process_info, opt_val)
        dest_opt_graph = self.get_opt_graph(dest_opt, dest_process_info)

        # Print arc
        print('"'+ orig_opt_graph +'"', "->", '"' + dest_opt_graph + '"', "[ dir=none ] ;")

    def get_fifo_opt(self, process_info, abs_fifoname):
        # Obtain necessary process information
        process_info_elems =  self.get_process_taskidx_elems(process_info)
        processname = process_info_elems[0]
        task_idx = int(process_info_elems[1])

        # Get option list
        opt_list = self.pplopts_exh[processname][task_idx]

        # Iterate over option list
        i = 0
        while i < len(opt_list) and opt_list[i] != abs_fifoname:
            i += 1

        # Return result
        if i < len(opt_list) and i > 0:
            return opt_list[i-1]
        else:
            return None

    def print_opt_to_opt_outval(self, process_info, opt, opt_val):
        # Iterate over processes producing opt_val
        for orig_procname, orig_taskidx, orig_opt in self.process_out_values[opt_val]:
            # Obtain origin node
            orig_process_info = self.get_process_taskidx_string(orig_procname, orig_taskidx)
            orig_opt_graph = self.get_opt_graph(orig_opt, orig_process_info)

            # Obtain destination node
            dest_opt_graph = self.get_opt_graph(opt, process_info)

            # Print arc
            print('"'+ orig_opt_graph +'"', "->", '"' + dest_opt_graph + '"', ";")
