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
NONE_STEP_DEP="none"

##################################################
class stepdep_data:
    def __init__(self):
        self.deptype=None
        self.stepname=None

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
    print("-d             Print dependencies for each step", file=sys.stderr)
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
def extract_step_name(entry):
    fields=entry.split()
    if len(fields)==0:
        return ""
    else:
        return fields[0]

##################################################
def get_dep_separator(sdeps_str):
    if ',' in sdeps_str and '?' in sdeps_str:
        return True,',?'
    elif ',' in sdeps_str:
        return False,','
    elif '?' in sdeps_str:
        return False,'?'
    else:
        return False,''
    
##################################################
def extract_step_deps(entry_lineno,entry):
    deps_syntax_ok=True
    # extract text field
    fields=entry.split()
    sdeps_str=""
    for f in fields:
        if f.find("stepdeps=")==0:
            sdeps_str=f[9:]

    # Return empty list of step dependencies if corresponding field was
    # not found
    if len(sdeps_str)==0:
        return deps_syntax_ok,[]

    # Check that dependency separators (, and ?) are not mixed
    seps_mixed,separator=get_dep_separator(sdeps_str)
    if seps_mixed:
        deps_syntax_ok=False
        print("Error: dependency separators mixed in step dependency (",sdeps_str,") at line number",entry_lineno, file=sys.stderr)
        return deps_syntax_ok,[]
    
    # create list of step dependencies
    sdeps_list=[]
    if(separator==''):
        sdeps_fields=[sdeps_str]
    else:
        sdeps_fields=sdeps_str.split(separator)
    for sdep in sdeps_fields:
        if sdep!=NONE_STEP_DEP:
            sdep_fields=sdep.split(":")
            if(len(sdep_fields)==2 and sdep_fields[1]!=''):
                data=stepdep_data()
                data.deptype=sdep_fields[0]
                data.stepname=sdep_fields[1]
                sdeps_list.append(data)
            else:
                deps_syntax_ok=False
                print("Error: incorrect definition of step dependency (",sdeps_str,") at line number",entry_lineno, file=sys.stderr)
        
    return deps_syntax_ok,separator,sdeps_list

##################################################
def extract_config_entries(pfile):
    config_entries=[]
    file = open(pfile, 'r')
    # read file entry by entry
    for entry in file:
        entry=entry.strip("\n")
        if entry_is_config(entry):
            config_entries.append(entry)
            
    return config_entries

##################################################
def extract_step_entries(pfile):
    entries_lineno=[]
    step_entries=[]
    file = open(pfile, 'r')
    # read file entry by entry
    lineno=1
    for entry in file:
        entry=entry.strip("\n")
        if not entry_is_comment(entry) and not entry_is_empty(entry):
            step_entries.append(entry)
            entries_lineno.append(lineno)
        lineno=lineno+1
        
    return entries_lineno,step_entries

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
def extract_steps_with_multiattempt(step_entries):
    multiattempt_steps=set()
    for i in range(len(step_entries)):
        sname=extract_step_name(step_entries[i])
        time_value=extract_time_value(step_entries[i])
        mem_value=extract_mem_value(step_entries[i])
        if(str_contains_commas(time_value) or str_contains_commas(mem_value)):
            multiattempt_steps.add(sname)
    return multiattempt_steps

##################################################
def extract_stepdeps_info(entries_lineno,step_entries):
    stepdeps_map={}
    stepdeps_sep={}
    deps_syntax_ok=True
    for i in range(len(step_entries)):
        fields=step_entries[i].split()
        sname=extract_step_name(step_entries[i])
        dep_syntax_ok,separator,deps=extract_step_deps(entries_lineno[i],step_entries[i])
        if(not dep_syntax_ok):
            deps_syntax_ok=False
        stepdeps_sep[sname]=separator
        stepdeps_map[sname]=deps
    return deps_syntax_ok,stepdeps_sep,stepdeps_map

##################################################
def stepnames_duplicated(entries_lineno,step_entries):
    stepnames=set()
    lineno=1
    for i in range(len(step_entries)):
        sname=extract_step_name(step_entries[i])
        if sname in stepnames:
            print("Error: step",sname,"in line",entries_lineno[i],"is duplicated", file=sys.stderr)
            return True
        else:
            stepnames.add(sname)
        lineno=lineno+1
    return False
    
##################################################
def depnames_correct(stepdeps_map):
    stepnames=set()
    stepdepnames=set()

    # Obtain sets of step names and names of step dependencies
    for stepname in stepdeps_map:
        stepnames.add(stepname)
        for elem in stepdeps_map[stepname]:
            stepdepnames.add(elem.stepname)

    for name in stepdepnames:
        if name not in stepnames:
            print("Error: unrecognized step dependency",name, file=sys.stderr)
            return False

    return True

##################################################
def stepname_can_be_added(sname,processed_steps,stepdeps_map):
    # Check if step name has already been added
    if sname in processed_steps:
        return False

    # Check if all dependencies for step name were processed
    for elem in stepdeps_map[sname]:
        if(elem.stepname not in processed_steps):
            return False
    
    return True
    
##################################################
def order_step_entries(step_entries,stepdeps_map,ordered_step_entries):
    processed_steps=set()
    # Add steps to ordered steps list incrementally
    while len(processed_steps)!=len(stepdeps_map):
        prev_proc_steps_len=len(processed_steps)
        # Explore list of step entries
        for entry in step_entries:
            sname=extract_step_name(entry)
            if(stepname_can_be_added(sname,processed_steps,stepdeps_map)):
                processed_steps.add(sname)
                ordered_step_entries.append(entry)
        # Check if no steps were added
        if(prev_proc_steps_len==len(processed_steps)):
            print("Error: the analysis file contains at least one cycle", file=sys.stderr)
            return ordered_step_entries
        
    return ordered_step_entries

##################################################
def after_dep_has_multatt_step(entries_lineno,multiattempt_steps,stepdeps_map):
    found=False
    for sname in stepdeps_map:
        deplist=stepdeps_map[sname]
        i=0
        while i<len(deplist) and not found:
            if(deplist[i].deptype=="after" and deplist[i].stepname in multiattempt_steps):
                found=True
                print("Error:",sname,"step has an 'after' dependency with a multiple-attempt step (",deplist[i].stepname,")", file=sys.stderr)
            else:
                i=i+1
    if(found):
        return True
    else:
        return False
    
##################################################
def stepdeps_correct(entries_lineno,step_entries,multiattempt_steps,stepdeps_map,ordered_step_entries):

    # Check existence of duplicated steps
    if(stepnames_duplicated(entries_lineno,step_entries)):
        return False
    
    # Check dependency names
    if(not depnames_correct(stepdeps_map)):
        return False

    # Check "after" dependency type is not used over a multi-attempt step
    if(after_dep_has_multatt_step(entries_lineno,multiattempt_steps,stepdeps_map)):
        return False
    # Reorder step entries
    order_step_entries(step_entries,stepdeps_map,ordered_step_entries)
    if(len(step_entries)!=len(ordered_step_entries)):
        return False
    
    return True

##################################################
def print_entries(config_entries,step_entries):
    for e in config_entries:
        print(e)
    for e in step_entries:
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
def print_graph(ordered_step_entries,stepdeps_sep,stepdeps_map):
    # Print header
    print("digraph G {")
    print("overlap=false;")
    print("splines=true;")
    print("K=1;")

    # Set representation for steps
    print("node [shape = ellipse];")

    # Process steps
    for step in stepdeps_map:
        line_style=get_graph_linestyle(stepdeps_sep[step])
        if len(stepdeps_map[step])==0:
            print("start","->",step, "[ label= \"\" ,","color = black ];")            
        else:
            for elem in stepdeps_map[step]:
                print(elem.stepname,"->",step, "[ label= \""+elem.deptype+"\" ,","style=",line_style,", color = black ];")
    
    # Print footer
    print("}")

##################################################
def extract_all_deps_for_step(sname,stepdeps_map,result):
    if sname in stepdeps_map:
        for stepdep in stepdeps_map[sname]:
            result.add(stepdep.stepname)
            extract_all_deps_for_step(stepdep.stepname,stepdeps_map,result)

##################################################
def print_deps(ordered_step_entries,stepdeps_map):
    for entry in ordered_step_entries:
        # Extract dependencies for step
        sname=extract_step_name(entry)
        stepdeps=set()
        extract_all_deps_for_step(sname,stepdeps_map,stepdeps)
        
        # Print dependencies for step
        depstr=""
        for dep in stepdeps:
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
def snames_valid(stepdeps_map):
    for sname in stepdeps_map:
        if(not sname_valid(sname)):
            print("Error: step name",sname,"contains not allowed characters (only letters, numbers and underscores are allowed)", file=sys.stderr)
            return 0
    return 1
    
##################################################
def process_pars(flags,values):
    config_entries=extract_config_entries(values["pfile"])
    entries_lineno,step_entries=extract_step_entries(values["pfile"])
    multiattempt_steps=extract_steps_with_multiattempt(step_entries)
    deps_syntax_ok,stepdeps_sep,stepdeps_map=extract_stepdeps_info(entries_lineno,step_entries)
    if(not deps_syntax_ok):
       print("Step dependencies are not syntactically correct", file=sys.stderr)
       return 1
    if(not snames_valid(stepdeps_map)):
       print("Step names are not valid", file=sys.stderr)
       return 1
    ordered_step_entries=[]
    if(stepdeps_correct(entries_lineno,step_entries,multiattempt_steps,stepdeps_map,ordered_step_entries)):
        print("Pipeline file is correct", file=sys.stderr)
        if(flags["r_given"]):
            print_entries(config_entries,ordered_step_entries)
        elif(flags["g_given"]):
            print_graph(ordered_step_entries,stepdeps_sep,stepdeps_map)
        elif(flags["d_given"]):
            print_deps(ordered_step_entries,stepdeps_map)
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
