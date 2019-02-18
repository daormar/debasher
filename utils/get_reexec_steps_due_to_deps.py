# *- python -*

# import modules
import io, sys, getopt, operator

# Constants
NONE_STEP_DEP="none"

##################################################
def take_pars():
    flags={}
    values={}
    flags["r_given"]=False
    flags["d_given"]=False
    values["verbose"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"r:d:v",["pfile="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-r", "--reexec-steps"):
                values["rexec_steps"] = arg
                flags["r_given"]=True
            elif opt in ("-d", "--depfile"):
                values["depfile"] = arg
                flags["d_given"]=True
            elif opt in ("-v", "--verbose"):
                flags["verbose"]=True
    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["r_given"]==False):
        print >> sys.stderr, "Error! -r parameter not given"
        sys.exit(2)

    if(flags["d_given"]==False):
        print >> sys.stderr, "Error! -d parameter not given"
        sys.exit(2)

##################################################
def print_help():
    print >> sys.stderr, "get_reexec_steps_due_to_deps -r <string> -d <string> [-v]"
    print >> sys.stderr, ""
    print >> sys.stderr, "-r <string>                  String with steps to be reexecuted"
    print >> sys.stderr, "-d <string>                  File with dependency information"
    print >> sys.stderr, "-v                           Verbose mode"

##################################################
def process_r_opt(rexec_steps_str):
    result=set()
    fields=rexec_steps_str.split(',')
    for step in fields:
        result.add(step)
    
    return result
    
##################################################
def load_dep_info(depfile):
    dep_info={}
    file = open(depfile, 'r')
    # read file entry by entry
    for entry in file:
        fields=entry.split()
        stepname=fields[0]
        deplist=[]
        for i in range(2,len(fields)):
            deplist.append(fields[i])
        dep_info[stepname]=deplist
        
    return dep_info
        
##################################################
def step_should_reexec(reexec_steps,step_deplist):
    for step in step_deplist:
        if step in reexec_steps:
            return True
    return False
    
##################################################
def get_new_reexec_steps(reexec_steps,curr_reexec_steps,dep_info):
    new_reexec_steps=set()
    for step in dep_info:
        if step not in reexec_steps and step_should_reexec(curr_reexec_steps,dep_info[step]):
            new_reexec_steps.add(step)
            
    return new_reexec_steps

##################################################
def get_reexec_steps_due_to_deps(initial_reexec_steps,dep_info):
    curr_reexec_steps=initial_reexec_steps
    reexec_steps=set()
    end=False
    while not end:
        curr_reexec_steps=get_new_reexec_steps(reexec_steps,curr_reexec_steps,dep_info)
        if (len(curr_reexec_steps)==0):
            end=True
        else:
            reexec_steps=reexec_steps.union(curr_reexec_steps)
        
    return reexec_steps

##################################################
def print_steps(reexec_steps):
    for step in reexec_steps:
        print step
    
##################################################
def process_pars(flags,values):
    initial_reexec_steps=process_r_opt(values["rexec_steps"])

    dep_info=load_dep_info(values["depfile"])
    
    reexec_steps_due_to_deps=get_reexec_steps_due_to_deps(initial_reexec_steps,dep_info)
    
    print_steps(reexec_steps_due_to_deps)
    
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
