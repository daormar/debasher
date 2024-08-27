# DeBasher package
# Copyright (C) 2019-2024 Daniel Ortiz-Mart\'inez
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

##############################
# PROGRAM-RELATED FUNCTIONS #
##############################

########
get_orig_workdir()
{
    local command_line_file=$1
    local workdir=`$HEAD -1 ${command_line_file} | "$AWK" '{print $2}'` ; pipe_fail || return 1
    echo $workdir
}

########
get_orig_outdir_from_command_line_file()
{
    # initialize variables
    local command_line_file=$1

    # Extract information from command line file
    local workdir
    workdir=`get_orig_workdir "${command_line_file}"` || return 1
    local cmdline
    cmdline=`get_cmdline_from_command_line_file "${command_line_file}"` || return 1
    local outdir=`read_opt_value_from_line "$cmdline" "--outdir"`

    # Retrieve original output directory
    if is_absolute_path "$outdir"; then
        echo "$outdir"
    else
        echo "${workdir}/${outdir}"
    fi
}

########
get_cmdline_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`"$TAIL" -1 "${command_line_file}"`
    sargsquotes_to_sargs "$cmdline"
}

########
get_pfile_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`get_cmdline_from_command_line_file "${command_line_file}"`
    local pfile=`read_opt_value_from_line "$cmdline" "--pfile"` || return 1
    echo "${pfile}"
}

########
get_currdir_from_command_line_file()
{
    local command_line_file=$1
    local currdir=`"${HEAD}" -1 "${command_line_file}" | "${AWK}" '{print $2}'`
    echo "${currdir}"
}

########
get_sched_from_command_line_file()
{
    local command_line_file=$1
    local cmdline=`get_cmdline_from_command_line_file "${command_line_file}"`
    local sched=`read_opt_value_from_line "${cmdline}" "--sched"` || return 1
    echo "${sched}"
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
get_abspfile_from_command_line_file()
{
    # Initialize variables
    local command_line_file=$1

    # Obtain program file and current dir
    local cmdline_pfile
    cmdline_pfile=`get_pfile_from_command_line_file "${command_line_file}"` || return 1
    local cmdline_currdir
    cmdline_currdir=`get_currdir_from_command_line_file "${command_line_file}"` || return 1

    # Obtain absolute program file name
    local abspfile
    pushd "${cmdline_currdir}" > /dev/null
    abspfile=`get_absolute_path "${cmdline_pfile}"`
    popd > /dev/null

    # Check if resulting program file exists
    if [ -f "${abspfile}" ]; then
        echo "${abspfile}"
        return 0
    else
        echo "Error: unable to find program file (${abspfile})" >&2
        return 1
    fi
}

########
exec_program_func_for_module()
{
    local pfile=$1

    local program_funcname
    program_funcname=`get_program_funcname "${pfile}"`

    ${program_funcname}
}

########
get_prg_exec_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_EXEC_DIRNAME}"
}

########
get_prg_exec_dir()
{
    get_prg_exec_dir_given_basedir "${PROGRAM_OUTDIR}"
}

########
get_prg_graphs_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${DEBASHER_GRAPHS_DIRNAME}"
}

########
get_prg_graphs_dir()
{
    get_prg_graphs_dir_given_basedir "${PROGRAM_OUTDIR}"
}

########
is_valid_processname() {
    local input="$1"
    if [[ "$input" =~ ^[a-zA-Z_]+$ ]]; then
        return 0  # True
    else
        return 1  # False
    fi
}

########
# Public: Reads the value of a given option from function arguments.
#
# $1 - Name of the process to add into the program.
# $2 - Computational specifications.
# $3 - Additional specifications for the process.
#
# Examples
#
#    add_debasher_process "file_writer" "cpus=1 mem=32 time=00:01:00"
#
# The function prints the process definition to the standard output.
# Additionally, it registers the process in a variable used by the
# DeBasher library.
add_debasher_process()
{
    # Initialize variables
    local processname=$1
    local process_computational_specs=$2
    local process_additional_specs=$3

    # Check correctness of process name and abort execution if necessary
    if ! is_valid_processname "${processname}"; then
        echo "Error: process name ${processname} not valid. It should contains letters or the underscore character. Aborting execution..." >&2
        exit 1
    fi

    # Print process program line
    echo "${processname}" "${process_computational_specs}" "${process_additional_specs}"

    # Store process name in associative array
    PROGRAM_PROCESSES["${processname}"]=1
}

########
apply_suffix_to_processdeps()
{
    local processdeps=$1
    local suffix=$2

    # Obtain process dependencies separated by blanks
    local separator=`get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi

    # Process dependencies
    local dep
    local result=""
    for dep in ${processdeps_blanks}; do
        # Extract dependency components
        local processname=`get_processname_part_in_dep ${dep}`
        local deptype=`get_deptype_part_in_dep ${dep}`
        # Obtain modified dependency
        if [ "${deptype}" = "${NONE_PROCESSDEP_TYPE}" ]; then
            local modified_dep="${deptype}"
        else
            local processname_with_suff=`get_processname_given_suffix "${processname}" "${suffix}"`
            local modified_dep="${deptype}${PROCESS_PLUS_DEPTYPE_SEP}${processname_with_suff}"
        fi
        # Add modified dependency to result
        if [ -z "${result}" ]; then
            result="${modified_dep}"
        else
            result="${result}${separator}${modified_dep}"
        fi
    done

    echo "${result}"
}

########
apply_suffix_to_program_entry()
{
    local prg_entry=$1
    local suffix=$2

    # Read the string into an array using the IFS
    local elements
    IFS=" " read -ra elements <<< "$prg_entry"

    # Initialize a variable to store the concatenated elements
    local result=""

    # Iterate over the indices of the elements array
    for i in "${!elements[@]}"; do
        # The first word is the process name
        if [ "${i}" -eq 0 ]; then
            # Add process with suffix to result
            local processname="${elements[$i]}"
            local processname_with_suff=`get_processname_given_suffix "${processname}" "${suffix}"`
            result="${processname_with_suff}"
        else
            if [[ "${elements[$i]}" == "${PROCESSDEPS_SPEC}"* ]]; then
                processdeps=`extract_processdeps_from_process_spec "${elements[$i]}"`
                processdeps_with_suffix=`apply_suffix_to_processdeps "${processdeps}" "${suffix}"`
                result="${result} ${PROCESSDEPS_SPEC}=${processdeps_with_suffix}"
            else
                result="${result} ${elements[$i]}"
            fi
        fi
    done

    # Print the concatenated result
    echo "$result"
}

########
add_debasher_program()
{
    # Initialize variables
    local modname=$1
    local suffix=$2

    # Create temporary file
    local tmpfile=`${MKTEMP}`

    # Execute program function for module and store output entries in a
    # temporary file (the purpose is to enable function execution
    # without using any sub-shell)
    exec_program_func_for_module "${modname}" > "${tmpfile}"

    # Process resulting program entries
    while read prg_entry; do
        apply_suffix_to_program_entry "${prg_entry}" "${suffix}" || return 1
    done < "${tmpfile}"

    # Remove temporary file
    "${RM}" "${tmpfile}"
}

########
program_uses_fifos()
{
    if [ "${#PROGRAM_FIFOS[@]}" -eq 0 ]; then
        return 1
    else
        return 0
    fi
}

########
get_number_of_program_fifos()
{
    echo "${#PROGRAM_FIFOS[@]}"
}
