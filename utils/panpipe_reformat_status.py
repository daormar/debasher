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
ROW_WITH_HEADER_FORMAT=1
ROW_WO_HEADER_FORMAT=2

##################################################
def take_pars():
    flags={}
    values={}
    flags["p_given"]=False
    values["pstatus"]=""
    flags["f_given"]=False
    flags["l_given"]=False
    flags["e_given"]=False
    
    try:
        opts, args = getopt.getopt(sys.argv[1:],"p:f:l:e:",["pstatus=","format=","fieldlen=","excl="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-p", "--pstatus"):
                values["pstatus"] = arg
                flags["p_given"]=True
            elif opt in ("-f", "--spec"):
                values["format"] = int(arg)
                flags["f_given"]=True
            elif opt in ("-l", "--fieldlen"):
                values["fieldlen"] = int(arg)
                flags["l_given"]=True
            elif opt in ("-e", "--excl"):
                values["excl"] = arg
                flags["e_given"]=True

    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["f_given"]==False):
        print("Error! -f parameter not given", file=sys.stderr)
        sys.exit(2)
    if(flags["l_given"]==False):
        print("Error! -l parameter not given", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("reformat_pipe_status [-p <string>] -f <int> -l <int> [-e <string>]", file=sys.stderr)
    print("", file=sys.stderr)
    print("-p <string>          File with pipe_status output (if not given,", file=sys.stderr)
    print("                     input is read from stdin)", file=sys.stderr)
    print("-f <int>             Output format:", file=sys.stderr)
    print("                     ",ROW_WITH_HEADER_FORMAT,"-> one row with header, plain text", file=sys.stderr)
    print("                     ",ROW_WO_HEADER_FORMAT,"-> one row without header, plain text", file=sys.stderr)
    print("-l <int>             Field length", file=sys.stderr)
    print("-e <string>          Comma-separated list of steps to be excluded", file=sys.stderr)

##################################################
def extract_step_info(pstatus):
    # Determine stream to be processed
    if pstatus=="":
        stream = sys.stdin
    else:
        stream = open(pstatus, 'r')

    # Process stream
    step_map={}
    for line in stream:
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
    if len(str)>=normlen:
        return str[0:normlen]
    else:
        result=""
        result += ' ' * normlen
        result +=str
        result=result[len(result)-normlen:]
        return result

##################################################
def print_step_info(step_map,excl_steps_set,format,fieldlen):
    if format==ROW_WITH_HEADER_FORMAT:
        header=""
        for step in step_map:
            if step not in excl_steps_set:
                if header=="":
                    header=norm_str_len(step,fieldlen)
                else:
                    header=header+" "+norm_str_len(step,fieldlen)
        print(header)

        status=""
        for step in step_map:
            if step not in excl_steps_set:
                if status=="":
                    status=norm_str_len(step_map[step],fieldlen)
                else:
                    status=status+" "+norm_str_len(step_map[step],fieldlen)
        print(status)
        
    elif format==ROW_WO_HEADER_FORMAT:
        status=""
        for step in step_map:
            if step not in excl_steps_set:
                if status=="":
                    status=norm_str_len(step_map[step],fieldlen)
                else:
                    status=status+" "+norm_str_len(step_map[step],fieldlen)
        print(status)
        
##################################################
def extract_excl_step_info(excl_steps):
    fields=excl_steps.split(",")
    excl_steps_set=set()
    for step in fields:
        excl_steps_set.add(step)
    return excl_steps_set
    
##################################################
def process_pars(flags,values):
    step_map=extract_step_info(values["pstatus"])
    excl_steps_set=set()
    if flags["e_given"]:
        excl_steps_set=extract_excl_step_info(values["excl"])
    print_step_info(step_map,excl_steps_set,values["format"],values["fieldlen"])
    
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
