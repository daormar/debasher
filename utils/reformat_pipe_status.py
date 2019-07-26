# *- python -*

# import modules
import io, sys, getopt, operator

# Constants
ROW_WITH_HEADER_FORMAT=1
ROW_WO_HEADER_FORMAT=2

##################################################
def take_pars():
    flags={}
    values={}
    flags["f_given"]=False
    flags["l_given"]=False
    
    try:
        opts, args = getopt.getopt(sys.argv[1:],"f:l:",["format=","fieldlen="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-f", "--spec"):
                values["format"] = int(arg)
                flags["f_given"]=True
            elif opt in ("-l", "--fieldlen"):
                values["fieldlen"] = int(arg)
                flags["l_given"]=True

    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["f_given"]==False):
        print >> sys.stderr, "Error! -f parameter not given"
        sys.exit(2)
    if(flags["l_given"]==False):
        print >> sys.stderr, "Error! -l parameter not given"
        sys.exit(2)

##################################################
def print_help():
    print >> sys.stderr, "reformat_pipe_status -f <int> -l <int>"
    print >> sys.stderr, ""
    print >> sys.stderr, "-f <int>             Output format:"
    print >> sys.stderr, "                     ",ROW_WITH_HEADER_FORMAT,"-> one row with header, plain text"
    print >> sys.stderr, "                     ",ROW_WO_HEADER_FORMAT,"-> one row without header, plain text"
    print >> sys.stderr, "-l <int>             Field length:"

##################################################
def extract_step_info():
    step_map={}
    # Read pipe_status output from standard input
    for line in sys.stdin:
        # Extract fields
        fields=line.split()

        # Extract step information
        if fields[0]=="STEP:":
            stepname=fields[1]
            status=fields[4]
            step_map[stepname]=status

    return step_map

##################################################
def norm_str_len(str,normlen):
    result=""
    result += ' ' * normlen
    result +=str
    result=result[len(result)-normlen:]
    return result

##################################################
def print_step_info(step_map,format,fieldlen):
    if format==ROW_WITH_HEADER_FORMAT:
        header=""
        for step in step_map:
            if header=="":
                header=norm_str_len(step,fieldlen)
            else:
                header=header+" "+norm_str_len(step,fieldlen)
        print header

        status=""
        for step in step_map:
            if status=="":
                status=norm_str_len(step_map[step],fieldlen)
            else:
                status=status+" "+norm_str_len(step_map[step],fieldlen)
        print status
        
    elif format==ROW_WO_HEADER_FORMAT:
        status=""
        for step in step_map:
            if status=="":
                status=norm_str_len(step_map[step],fieldlen)
            else:
                status=status+" "+norm_str_len(step_map[step],fieldlen)
        print status
        
##################################################
def process_pars(flags,values):
    step_map=extract_step_info()
    print_step_info(step_map,values["format"],values["fieldlen"])
    
##################################################
def main(argv):
    # take parameters
    (flags,values)=take_pars()

    # check parameters
    check_pars(flags,values)

    # process parameters
    process_pars(flags,values)
    
if __name__ == "__main__":
    main(sys.argv)