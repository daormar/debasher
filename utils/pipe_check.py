# *- python -*

# import modules
import io, sys, getopt, operator

# Constants
NONE_JOB_DEP="none"

##################################################
class jobdep_data:
    def __init__(self):
        self.deptype=None
        self.jobname=None

##################################################
def take_pars():
    flags={}
    values={}
    flags["a_given"]=False
    flags["r_given"]=False
    flags["g_given"]=False
    values["verbose"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"a:rgv",["afile="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-a", "--afile"):
                values["afile"] = arg
                flags["a_given"]=True
            elif opt in ("-r", "--print-reord"):
                flags["r_given"]=True
            elif opt in ("-g", "--print-graph"):
                flags["g_given"]=True
            elif opt in ("-v", "--verbose"):
                flags["verbose"]=True
    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["a_given"]==False):
        print >> sys.stderr, "Error! -a parameter not given"
        sys.exit(2)

    if(flags["r_given"] and flags["g_given"]):
        print >> sys.stderr, "Error! -r and -g parameters cannot be given simultaneously"
        sys.exit(2)

##################################################
def print_help():
    print >> sys.stderr, "check_pipeline -a <string> [-r|-g] [-v]"
    print >> sys.stderr, ""
    print >> sys.stderr, "-a <string>    Analysis file"
    print >> sys.stderr, "-r             Print reordered pipeline"
    print >> sys.stderr, "-g             Print pipeline in graphviz format"
    print >> sys.stderr, "-v             Verbose mode"

##################################################
def entry_is_comment(entry):
    fields=entry.split()
    if fields[0][0]=="#":
        return True
    else:
        return False

##################################################
def extract_job_name(entry):
    fields=entry.split()
    return fields[0]

##################################################
def extract_job_deps(entry):
    # extract text field
    fields=entry.split()
    for f in fields:
        if f.find("jobdeps=")==0:
            jdeps_str=f[8:]

    # Return empty list of job dependencies if corresponding field was
    # not found
    if len(jdeps_str)==0:
        return []
    
    # create list of job dependencies
    jdeps_list=[]
    jdeps_fields=jdeps_str.split(",")
    for jdep in jdeps_fields:
        if jdep!=NONE_JOB_DEP:
            jdep_fields=jdep.split(":")
            data=jobdep_data()
            data.deptype=jdep_fields[0]
            data.jobname=jdep_fields[1]
            jdeps_list.append(data)
        
    return jdeps_list
        
##################################################
def extract_job_entries(afile):
    job_entries=[]
    file = open(afile, 'r')
    # read file entry by entry
    for entry in file:
        entry=entry.strip("\n")
        if not entry_is_comment(entry):
            job_entries.append(entry)
            
    return job_entries

##################################################
def create_jobdeps_map(job_entries):
    jobdeps_map={}
    for entry in job_entries:
        jname=extract_job_name(entry)
        deps=extract_job_deps(entry)
        jobdeps_map[jname]=deps
    return jobdeps_map

##################################################
def jobnames_duplicated(job_entries):
    jobnames=set()
    lineno=1
    for entry in job_entries:
        jname=extract_job_name(entry)
        if jname in jobnames:
            print >> sys.stderr, "Error: duplicated job name in line",lineno
            return True
        else:
            jobnames.add(jname)
        lineno=lineno+1
    return False
    
##################################################
def depnames_correct(jobdeps_map):
    jobnames=set()
    jobdepnames=set()

    # Obtain sets of job names and names of job dependencies
    for jobname in jobdeps_map:
        jobnames.add(jobname)
        for elem in jobdeps_map[jobname]:
            jobdepnames.add(elem.jobname)

    for name in jobdepnames:
        if name not in jobnames:
            print >> sys.stderr, "Error: unrecognized job dependency",name
            return False

    return True

##################################################
def jobname_can_be_added(jname,processed_jobs,jobdeps_map):
    # Check if job name has already been added
    if jname in processed_jobs:
        return False

    # Check if all dependencies for job name were processed
    for elem in jobdeps_map[jname]:
        if(elem.jobname not in processed_jobs):
            return False
    
    return True
    
##################################################
def order_job_entries(job_entries,jobdeps_map,ordered_job_entries):
    processed_jobs=set()
    # Add jobs to ordered jobs list incrementally
    while len(processed_jobs)!=len(jobdeps_map):
        prev_proc_jobs_len=len(processed_jobs)
        # Explore list of job entries
        for entry in job_entries:
            jname=extract_job_name(entry)
            if(jobname_can_be_added(jname,processed_jobs,jobdeps_map)):
                processed_jobs.add(jname)
                ordered_job_entries.append(entry)
        # Check if no jobs were added
        if(prev_proc_jobs_len==len(processed_jobs)):
            print >> sys.stderr, "Error: the analysis file contains at least one cycle"
            return ordered_job_entries
        
    return ordered_job_entries
    
##################################################
def jobdeps_correct(job_entries,jobdeps_map,ordered_job_entries):

    # Check existence of duplicated jobs
    if(jobnames_duplicated(job_entries)):
        return False
    
    # Check dependency names
    if(not depnames_correct(jobdeps_map)):
        return False

    # Reorder job entries
    order_job_entries(job_entries,jobdeps_map,ordered_job_entries)
    if(len(job_entries)!=len(ordered_job_entries)):
        return False
    
    return True

##################################################
def print_entries(entries):
    for e in entries:
        print e

##################################################
def print_graph(ordered_job_entries,jobdeps_map):
    # Print header
    print "digraph G {"
#    print "rankdir=LR;"
    print "overlap=false;"
    print "splines=true;"
    print "K=1;"

    # Set representation for steps
    print "node [shape = ellipse];"

    # Process jobs
    for job in jobdeps_map:
        if len(jobdeps_map[job])==0:
            print "start","->",job, "[ label= \"\" ,","color = black ];"            
        else:
            for elem in jobdeps_map[job]:
                print elem.jobname,"->",job, "[ label= \""+elem.deptype+"\" ,","color = black ];"
    
    # Print footer
    print "}"
    
##################################################
def process_pars(flags,values):
    job_entries=extract_job_entries(values["afile"])
    jobdeps_map=create_jobdeps_map(job_entries)
    ordered_job_entries=[]
    if(jobdeps_correct(job_entries,jobdeps_map,ordered_job_entries)):
        print >> sys.stderr, "Pipeline file is correct"
        if(flags["r_given"]):
            print_entries(ordered_job_entries)
        elif(flags["g_given"]):
            print_graph(ordered_job_entries,jobdeps_map)
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
