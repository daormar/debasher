# PanPipe package
# Copyright (C) 2019,2020 Daniel Ortiz-Mart\'inez
#  
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#  
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#  
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.
  
# *- bash -*

# INCLUDE BASH LIBRARY
. "${panpipe_bindir}"/panpipe_lib || exit 1

########
print_desc()
{
    echo "pipe_stats gets statistics about pipeline steps"
    echo "type \"pipe_stats --help\" to get usage information"
}

########
usage()
{
    echo "pipe_stats                -d <string> [-s <string>]"
    echo "                          [--help]"
    echo ""
    echo "-d <string>               Output directory for pipeline steps"
    echo "-s <string>               Step name whose statistics should be obtained"
    echo "--help                    Display this help and exit"
}

########
read_pars()
{
    d_given=0
    s_given=0
    while [ $# -ne 0 ]; do
        case $1 in
            "--help") usage
                      exit 1
                      ;;
            "-d") shift
                  if [ $# -ne 0 ]; then
                      pdir=$1
                      d_given=1
                  fi
                  ;;
            "-s") shift
                  if [ $# -ne 0 ]; then
                      given_stepname=$1
                      s_given=1
                  fi
                  ;;
        esac
        shift
    done   
}

########
check_pars()
{
    if [ ${d_given} -eq 0 ]; then
        echo "Error! -d parameter not given!" >&2
        exit 1
    else
        if [ ! -d "${pdir}" ]; then
            echo "Error! pipeline directory does not exist" >&2 
            exit 1
        fi

        if [ ! -f "${pdir}"/command_line.sh ]; then
            echo "Error! ${pdir}/command_line.sh file is missing" >&2 
            exit 1
        fi
    fi
}

########
get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 "${command_line_file}" | "$AWK" '{print $2}'` ; pipe_fail || return 1
    echo "$workdir"
}

########
get_orig_outdir()
{
    # initialize variables
    local command_line_file=$1

    # Extract information from command line file
    local workdir
    workdir=`get_orig_workdir "${command_line_file}"` || return 1
    local cmdline
    cmdline=`get_cmdline "${command_line_file}"` || return 1
    local outdir=`read_opt_value_from_line "$cmdline" "--outdir"`

    # Retrieve original output directory
    if is_absolute_path "$outdir"; then
        echo "$outdir"
    else
        echo "${workdir}/${outdir}"
    fi
}

########
get_cmdline()
{
    local command_line_file=$1
    local cmdline=`"$TAIL" -1 ${command_line_file}`
    echo "$cmdline"
}

########
get_cmdline_pfile()
{
    local command_line_file=$1
    local cmdline=`"$TAIL" -1 "${command_line_file}"`
    local pfile=`read_opt_value_from_line "$cmdline" "--pfile"` || return 1
    echo "$pfile"
}

########
get_sched()
{
    local command_line_file=$1
    local cmdline=`"$TAIL" -1 "${command_line_file}"`
    local sched=`read_opt_value_from_line "$cmdline" "--sched"` || return 1
    echo "$sched"
}

########
replace_outdir_in_cmdline()
{
    local cmdline=$1
    local newdir=$2

    echo "$cmdline" | "$AWK" -v newdir="$newdir" 'BEGIN{
                                replace=0
                               }
                               {
                                for(i=1;i<=NF;++i)
                                {
                                 if(replace==0)
                                 {
                                  printf"%s",$i
                                 } 
                                 else
                                 {
                                  printf"%s",newdir
                                  replace=0
                                 }
                                 if($i=="--outdir") replace=1
                                 if(i!=NF) printf" "
                                }
                               }'
}

########
get_pfile()
{
    local absdirname=$1
    local cmdline_pfile=$2
    
    if [ -f "${absdirname}/${REORDERED_PIPELINE_BASENAME}" ]; then
        echo "${absdirname}/${REORDERED_PIPELINE_BASENAME}"
        return 0
    else
        if [ -f "${cmdline_pfile}" ]; then
            echo "${cmdline_pfile}"
            return 0
        else
            echo "Error: unable to find pipeline file (${cmdline_pfile})" >&2
            return 1
        fi
    fi
}

########
configure_scheduler()
{
    local sched=$1
    if [ ${sched} != ${OPT_NOT_FOUND} ]; then
        set_panpipe_scheduler ${sched} || return 1
    fi
}

########
process_status_for_pfile()
{
    local dirname=$1
    local absdirname=`get_absolute_path "${dirname}"`
    local command_line_file="${absdirname}"/command_line.sh

    # Extract information from command_line.sh file
    local cmdline
    cmdline=`get_cmdline "${command_line_file}"` || return 1
    local cmdline_pfile
    cmdline_pfile=`get_cmdline_pfile "${command_line_file}"` || return 1
    local sched
    sched=`get_sched "${command_line_file}"` || return 1

    # Set pipeline file
    local pfile
    pfile=`get_pfile "${absdirname}" "${cmdline_pfile}"` || return 1
    
    # Get original output directory
    local orig_outdir
    orig_outdir=`get_orig_outdir "${command_line_file}"` || return 1

    # Show warning if directory provided as option is different than the
    # original working directory
    if dirnames_are_equal "${orig_outdir}" "${absdirname}"; then
        local moved_outdir="no"        
    else
        echo "Warning: pipeline output directory was moved (original directory: ${orig_outdir})" >&2
        cmdline=`replace_outdir_in_cmdline "${cmdline}" "${absdirname}"`
        local moved_outdir="yes"
    fi

    # Load pipeline modules
    load_pipeline_modules "$pfile" || return 1

    # Configure scheduler
    configure_scheduler $sched || return 1
    
    # Read information about the steps to be executed
    lineno=1
    num_steps=0
    while read stepspec; do
        local stepspec_comment=`pipeline_stepspec_is_comment "$stepspec"`
        local stepspec_ok=`pipeline_stepspec_is_ok "$stepspec"`
        if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "yes" ]; then
            # Increase number of steps
            num_steps=$((num_steps + 1))
            
            # Extract step information
            local stepname=`extract_stepname_from_stepspec "$stepspec"`

            # If s option was given, continue to next iteration if step
            # name does not match with the given one
            if [ ${s_given} -eq 1 -a "${given_stepname}" != $stepname ]; then
                continue
            fi

            # Check step status
            local status=`get_step_status "${absdirname}" ${stepname}`

            # Get elapsed time if step finished
            elapsed_time=`get_elapsed_time_for_step "${absdirname}" ${stepname}`
            
            # Print status
            echo "STEP: $stepname ; STATUS: $status ; ELAPSED_TIME(s): ${elapsed_time}"                        
        else
            if [ ${stepspec_comment} = "no" -a ${stepspec_ok} = "no" ]; then
                echo "Error: incorrect step specification at line $lineno of ${pfile}" >&2
                return 1
            fi
        fi
        
        # Increase lineno
        lineno=$((lineno+1))
        
    done < "${pfile}"
}

########

if [ $# -eq 0 ]; then
    print_desc
    exit 1
fi

read_pars "$@" || exit 1

check_pars || exit 1

process_status_for_pfile "${pdir}" "${pfile}"

exit $?
