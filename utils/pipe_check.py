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
        print >> sys.stderr, "Error! -p parameter not given"
        sys.exit(2)

    if(flags["r_given"] and flags["g_given"]):
        print >> sys.stderr, "Error! -r and -g options cannot be given simultaneously"
        sys.exit(2)

    if(flags["r_given"] and flags["d_given"]):
        print >> sys.stderr, "Error! -r and -d options cannot be given simultaneously"
        sys.exit(2)

    if(flags["g_given"] and flags["d_given"]):
        print >> sys.stderr, "Error! -g and -d options cannot be given simultaneously"
        sys.exit(2)

##################################################
def print_help():
    print >> sys.stderr, "pipe_check     -p <string> [-r|-g|-d] [-v]"
    print >> sys.stderr, ""
    print >> sys.stderr, "-p <string>    Pipeline file"
    print >> sys.stderr, "-r             Print reordered pipeline"
    print >> sys.stderr, "-g             Print pipeline in graphviz format"
    print >> sys.stderr, "-d             Print dependencies for each step"
    print >> sys.stderr, "-v             Verbose mode"

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
def extract_step_deps(entry):
    # extract text field
    fields=entry.split()
    sdeps_str=""
    for f in fields:
        if f.find("stepdeps=")==0:
            sdeps_str=f[9:]

    # Return empty list of step dependencies if corresponding field was
    # not found
    if len(sdeps_str)==0:
        return []
    
    # create list of step dependencies
    sdeps_list=[]
    sdeps_fields=sdeps_str.split(",")
    for sdep in sdeps_fields:
        if sdep!=NONE_STEP_DEP:
            sdep_fields=sdep.split(":")
            if(len(sdep_fields)==2):
                data=stepdep_data()
                data.deptype=sdep_fields[0]
                data.stepname=sdep_fields[1]
                sdeps_list.append(data)
            else:
                print >> sys.stderr, "Error: incorrect definition of step dependency (",sdeps_str,")"
        
    return sdeps_list

##################################################
def extract_config_entries(pfile):
    step_entries=[]
    file = open(pfile, 'r')
    # read file entry by entry
    for entry in file:
        entry=entry.strip("\n")
        if entry_is_config(entry):
            step_entries.append(entry)
            
    return step_entries

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
def create_stepdeps_map(step_entries):
    stepdeps_map={}
    for entry in step_entries:
        fields=entry.split()
        sname=extract_step_name(entry)
        deps=extract_step_deps(entry)
        stepdeps_map[sname]=deps
    return stepdeps_map

##################################################
def stepnames_duplicated(entries_lineno,step_entries):
    stepnames=set()
    lineno=1
    for i in range(len(step_entries)):
        sname=extract_step_name(step_entries[i])
        if sname in stepnames:
            print >> sys.stderr, "Error: step",sname,"in line",entries_lineno[i],"is duplicated"
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
            print >> sys.stderr, "Error: unrecognized step dependency",name
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
            print >> sys.stderr, "Error: the analysis file contains at least one cycle"
            return ordered_step_entries
        
    return ordered_step_entries
    
##################################################
def stepdeps_correct(entries_lineno,step_entries,stepdeps_map,ordered_step_entries):

    # Check existence of duplicated steps
    if(stepnames_duplicated(entries_lineno,step_entries)):
        return False
    
    # Check dependency names
    if(not depnames_correct(stepdeps_map)):
        return False

    # Reorder step entries
    order_step_entries(step_entries,stepdeps_map,ordered_step_entries)
    if(len(step_entries)!=len(ordered_step_entries)):
        return False
    
    return True

##################################################
def print_entries(config_entries,step_entries):
    for e in config_entries:
        print e
    for e in step_entries:
        print e

##################################################
def print_graph(ordered_step_entries,stepdeps_map):
    # Print header
    print "digraph G {"
    print "overlap=false;"
    print "splines=true;"
    print "K=1;"

    # Set representation for steps
    print "node [shape = ellipse];"

    # Process steps
    for step in stepdeps_map:
        if len(stepdeps_map[step])==0:
            print "start","->",step, "[ label= \"\" ,","color = black ];"            
        else:
            for elem in stepdeps_map[step]:
                print elem.stepname,"->",step, "[ label= \""+elem.deptype+"\" ,","color = black ];"
    
    # Print footer
    print "}"

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
        print sname,":",depstr

##################################################
def process_pars(flags,values):
    config_entries=extract_config_entries(values["pfile"])
    entries_lineno,step_entries=extract_step_entries(values["pfile"])
    stepdeps_map=create_stepdeps_map(step_entries)
    ordered_step_entries=[]
    if(stepdeps_correct(entries_lineno,step_entries,stepdeps_map,ordered_step_entries)):
        print >> sys.stderr, "Pipeline file is correct"
        if(flags["r_given"]):
            print_entries(config_entries,ordered_step_entries)
        elif(flags["g_given"]):
            print_graph(ordered_step_entries,stepdeps_map)
        elif(flags["d_given"]):
            print_deps(ordered_step_entries,stepdeps_map)
    else:
        print >> sys.stderr, "Pipeline file is not correct"
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
