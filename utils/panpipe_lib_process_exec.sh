###############################
# PROCESS EXECUTION FUNCTIONS #
###############################

########
get_script_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}"
}

########
get_processid_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/$processname.${PROCESSID_FEXT}"
}

########
get_array_taskid_filename()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_${idx}.${ARRAY_TASKID_FEXT}"
}

########
get_array_taskid()
{
    local dirname=$1
    local processname=$2
    local idx=$3

    file=`get_array_taskid_filename "${dirname}" ${processname} ${idx}`
    if [ -f "${file}" ]; then
        cat "$file"
    else
        echo ${INVALID_ARRAY_TID}
    fi
}

########
get_process_finished_filename()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.${FINISHED_PROCESS_FEXT}"
}

########
get_process_log_filename_builtin()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.${BUILTIN_SCHED_LOG_FEXT}"
}

########
get_task_log_filename_builtin()
{
    local dirname=$1
    local processname=$2
    local taskidx=$3

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_${taskidx}.${BUILTIN_SCHED_LOG_FEXT}"
}

########
get_process_log_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.${SLURM_SCHED_LOG_FEXT}"
}

########
get_process_last_attempt_logf_slurm()
{
    local dirname=$1
    local processname=$2

    # Obtain number of log files
    local logfname=`get_process_log_filename_slurm "$dirname" $processname`
    local numlogf=0
    for f in "${logfname}"*; do
        numlogf=$((numlogf + 1))
    done

    # Echo name of last attempt
    if [ ${numlogf} -eq 0 ]; then
        echo ${NOFILE}
    else
        local suff=`get_slurm_attempt_suffix ${numlogf}`
        echo "${logfname}${suff}"
    fi
}

########
get_process_log_preverif_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.preverif.${SLURM_SCHED_LOG_FEXT}"
}

########
get_process_log_verif_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.verif.${SLURM_SCHED_LOG_FEXT}"
}

########
get_process_log_signcomp_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.signcomp.${SLURM_SCHED_LOG_FEXT}"
}

########
get_task_log_filename_slurm()
{
    local dirname=$1
    local processname=$2
    local taskidx=$3

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_${taskidx}.${SLURM_SCHED_LOG_FEXT}"
}

########
get_task_last_attempt_logf_slurm()
{
    local dirname=$1
    local processname=$2
    local taskidx=$3

    # Obtain number of log files
    local logfname=`get_task_log_filename_slurm "$dirname" $processname $taskidx`
    local numlogf=0
    for f in "${logfname}*"; do
        numlogf=$((numlogf + 1))
    done

    # Echo name of last attempt
    if [ ${numlogf} -eq 0 ]; then
        echo ${NOFILE}
    else
        local suff=`get_slurm_attempt_suffix ${numlogf}`
        echo "${logfname}${suff}"
    fi
}

########
get_task_template_log_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}_%a.${SLURM_SCHED_LOG_FEXT}"
}

########
remove_suffix_from_processname()
{
    local processname=$1

    echo ${processname} | "$AWK" '{if(index($1,"__")==0){print $1} else{printf "%s\n",substr($1,1,index($1,"__")-1)}}'
}

########
get_name_of_process_function_reset()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    local process_function_reset="${processname_wo_suffix}_reset_outdir"

    if func_exists ${process_function_reset}; then
        echo ${process_function_reset}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_name_of_process_function()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    echo "${processname_wo_suffix}"
}

########
get_name_of_process_function_post()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    local process_function_post="${processname_wo_suffix}_post"

    if func_exists ${process_function_post}; then
        echo ${process_function_post}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_name_of_process_function_outdir()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    local process_function_outdir="${processname_wo_suffix}_outdir_basename"

    if func_exists ${process_function_outdir}; then
        echo ${process_function_outdir}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_explain_cmdline_opts_funcname()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    echo ${processname_wo_suffix}_explain_cmdline_opts
}

########
get_define_opts_funcname()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    echo ${processname_wo_suffix}_define_opts
}

########
get_execute_funcname()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    local process_execute_function="${processname_wo_suffix}_execute"
    if func_exists ${process_execute_function}; then
        echo ${process_execute_function}
    else
        echo ${FUNCT_NOT_FOUND}
    fi
}

########
get_conda_envs_funcname()
{
    local processname=$1

    local processname_wo_suffix=`remove_suffix_from_processname ${processname}`

    echo ${processname_wo_suffix}_conda_envs
}

########
define_opts_for_script()
{
    local cmdline=$1
    local process_spec=$2
    local processname=`extract_processname_from_process_spec "$process_spec"`

    clear_opt_list_array
    local define_opts_funcname=`get_define_opts_funcname ${processname}`
    ${define_opts_funcname} "${cmdline}" "${process_spec}" || return 1
}

########
get_processdeps_separator()
{
    local processdeps=$1
    if [[ "${processdeps}" == *","* ]]; then
        echo ","
    else
        if [[ "${processdeps}" == *"?"* ]]; then
            echo "?"
        else
            echo ""
        fi
    fi
}

########
find_dependency_for_process()
{
    local process_spec=$1
    local processname_part=$2

    local processdeps=`extract_processdeps_from_process_spec "$process_spec"`
    local separator=`get_processdeps_separator ${processdeps}`
    if [ "${separator}" = "" ]; then
        local processdeps_blanks=${processdeps}
    else
        local processdeps_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processdeps}`
    fi
    local dep
    for dep in ${processdeps_blanks}; do
        local processname_part_in_dep=`get_processname_part_in_dep ${dep}`
        if [ "${processname_part_in_dep}" = ${processname_part} ]; then
            echo ${dep}
            return 0
        fi
    done
    echo ${DEP_NOT_FOUND}
    return 1
}

########
get_ppl_outd()
{
    echo "${PIPELINE_OUTDIR}"
}

########
get_ppl_scripts_dir_given_basedir()
{
    local dirname=$1

    echo "${dirname}/${PANPIPE_SCRIPTS_DIRNAME}"
}

########
get_ppl_scripts_dir()
{
    get_ppl_scripts_dir_given_basedir "${PIPELINE_OUTDIR}"
}

########
get_ppl_scripts_dir_for_process()
{
    local dirname=$1
    local processname=$2

    # Get base scripts dir
    scriptsdir=`get_ppl_scripts_dir_given_basedir "${dirname}"`

    echo "${scriptsdir}"
}

########
get_outd_for_dep()
{
    local dep=$1

    if [ -z "${dep}" ]; then
        echo ""
    else
        # Get name of output directory
        local outd="${PIPELINE_OUTDIR}"

        # Get processname
        local processname_part=`echo ${dep} | "$AWK" -F ":" '{print $2}'`

        get_process_outdir_given_dirname "${outd}" ${processname_part}
    fi
}

########
get_outd_for_dep_given_process_spec()
{
    local process_spec=$1
    local depname=$2

    local dep=`find_dependency_for_process "${process_spec}" $depname`
    if [ ${dep} = ${DEP_NOT_FOUND} ]; then
        return 1
    else
        local outd=`get_outd_for_dep "${dep}"`
        echo "${outd}"
        return 0
    fi
}

########
apply_deptype_to_processids()
{
    # Initialize variables
    local processids=$1
    local deptype=$2

    # Apply deptype
    local result=""
    local separator=`get_processdeps_separator ${processids}`
    if [ "${separator}" = "" ]; then
        local processids_blanks=${processids}
    else
        local processids_blanks=`replace_str_elem_sep_with_blank "${separator}" ${processids}`
    fi
    local id
    for id in ${processids_blanks}; do
        if [ -z "" ]; then
            result=${deptype}:${id}
        else
            result=${result}"${separator}"${deptype}:${id}
        fi
    done

    echo $result
}

########
get_list_of_pending_tasks_in_array()
{
    # NOTE: a pending task here is just one that is not finished
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Create associative map containing completed jobs
    local -A completed_tasks
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ -f "${finished_filename}" ]; then
        while read line; do
            local fields=( $line )
            local num_fields=${#fields[@]}
            if [ ${num_fields} -eq 7 ]; then
                local id=${fields[3]}
                completed_tasks[${id}]="1"
            fi
        done < "${finished_filename}"
    fi

    # Create string enumerating pending tasks
    local pending_tasks=""
    local idx=1
    while [ $idx -le ${array_size} ]; do
        if [ -z "${completed_tasks[${idx}]}" ]; then
            if [ -z "${pending_tasks}" ]; then
                pending_tasks=${idx}
            else
                pending_tasks="${pending_tasks},${idx}"
            fi
        fi
        idx=$((idx + 1))
    done

    echo ${pending_tasks}
}

########
get_task_array_list()
{
    local dirname=$1
    local processname=$2
    local array_size=$3
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`

    if [ -f "${finished_filename}" ]; then
        # Some jobs were completed, return list containing pending ones
        get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}
    else
        # No jobs were completed, return list containing all of them
        echo "1-${array_size}"
    fi
}

########
get_deptype_part_in_dep()
{
    local dep=$1
    local sep=":"
    local str_array
    IFS="$sep" read -r -a str_array <<< "${dep}"

    echo ${str_array[0]}
}

########
get_processname_part_in_dep()
{
    local dep=$1
    if [ ${dep} = "none" ]; then
        echo ${dep}
    else
        local sep=":"
        local str_array
        IFS="$sep" read -r -a str_array <<< "${dep}"
        echo ${str_array[1]}
    fi
}

########
get_id_part_in_dep()
{
    local dep=$1
    local sep=":"
    local str_array
    IFS="$sep" read -r -a str_array <<< "${dep}"
    echo ${str_array[1]}
}

########
task_array_elem_is_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        return 0
    else
        return 1
    fi
}

########
get_start_idx_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[0]}
    else
        echo "-1"
    fi
}

########
get_end_idx_in_range()
{
    local elem=$1
    local array
    IFS='-' read -r -a array <<< "$elem"
    numfields=${#array[@]}
    if [ $numfields -eq 2 ]; then
        echo ${array[1]}
    else
        echo "-1"
    fi
}

########
get_default_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2
    echo "${dirname}/${processname}"
}

########
get_process_outdir_given_dirname()
{
    local dirname=$1
    local processname=$2

    # Get name of process function to set output directory
    process_function_outdir=`get_name_of_process_function_outdir ${processname}`

    if [ "${process_function_outdir}" = "${FUNCT_NOT_FOUND}" ]; then
        get_default_process_outdir_given_dirname "$dirname" $processname
    else
        outdir_basename=`process_function_outdir`
        echo "${dirname}/${outdir_basename}"
    fi
}

########
get_process_outdir()
{
    local processname=$1

    # Get full path of output directory
    local outd=${PIPELINE_OUTDIR}

    get_process_outdir_given_dirname "${outd}" "${processname}"
}

########
create_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" ${processname}`

    if [ -d ${outd} ]; then
        echo "Warning: ${processname} output directory already exists but pipeline was not finished or will be re-executed, directory content will be removed">&2
    else
        mkdir "${outd}" || { echo "Error! cannot create output directory" >&2; return 1; }
    fi
}

########
default_reset_outdir_for_process()
{
    local dirname=$1
    local processname=$2
    local outd=`get_process_outdir_given_dirname "${dirname}" ${processname}`

    if [ -d "${outd}" ]; then
        echo "* Resetting output directory for process...">&2
        rm -rf "${outd}"/* || { echo "Error! could not clear output directory" >&2; return 1; }
    fi
}

########
default_reset_outdir_for_process_array()
{
    :
}

########
update_process_completion_signal()
{
    local dirname=$1
    local processname=$2
    local status=$3

    # If process will be reexecuted, file signaling process completion should
    # be removed. Additionally, this action should be registered in a
    # specific associative array
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    if [ "${status}" = "${REEXEC_PROCESS_STATUS}" ]; then
        rm -f "${finished_filename}"
        PANPIPE_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]=1
    fi
}

########
clean_process_log_files_slurm()
{
    local dirname=$1
    local processname=$2
    local array_size=$3
    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local slurm_log_filename=`get_process_log_filename_slurm "${dirname}" ${processname}`
        rm -f "${slurm_log_filename}*"
        local slurm_log_preverif=`get_process_log_preverif_filename_slurm "${dirname}" ${processname}`
        rm -f "${slurm_log_preverif}"
        local slurm_log_verif=`get_process_log_verif_filename_slurm "${dirname}" ${processname}`
        rm -f "${slurm_log_verif}"
        local slurm_log_signcomp=`get_process_log_signcomp_filename_slurm "${dirname}" ${processname}`
        rm -f "${slurm_log_signcomp}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local slurm_task_log_filename=`get_task_log_filename_slurm "${dirname}" ${processname} ${idx}`
                rm -f "${slurm_task_log_filename}*"
            done
        fi
    fi
}

########
clean_process_log_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    local sched=`determine_scheduler`
    case $sched in
        ${SLURM_SCHEDULER})
            clean_process_log_files_slurm "$dirname" $processname $array_size
            ;;
    esac
}

########
clean_process_id_files()
{
    local dirname=$1
    local processname=$2
    local array_size=$3

    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        local processid_file=`get_processid_filename "${dirname}" ${processname}`
        rm -f "${processid_file}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            local pending_tasks_blanks=`replace_str_elem_sep_with_blank "," ${pending_tasks}`
            for idx in ${pending_tasks_blanks}; do
                local array_taskid_file=`get_array_taskid_filename "${dirname}" ${processname} ${idx}`
                rm -f "${array_taskid_file}"
            done
        fi
    fi
}

########
write_process_id_info_to_file()
{
    local dirname=$1
    local processname=$2
    local id_info=$3
    local filename=`get_processid_filename "${dirname}" ${processname}`

    echo ${id_info} > "$filename"
}

########
read_process_id_info_from_file()
{
    local dirname=$1
    local processname=$2

    # Return id for process
    local filename=`get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        cat "$filename"
    else
        echo ${INVALID_SID}
    fi
}

########
read_ids_from_files()
{
    local dirname=$1
    local processname=$2
    local ids

    # Return id for process
    local filename=`get_processid_filename "${dirname}" ${processname}`
    if [ -f "$filename" ]; then
        ids=`cat "$filename"`
    fi

    # Get scripts dir
    scriptsdir=`get_ppl_scripts_dir_given_basedir "${dirname}"`

    # Return ids for array tasks if any
    local id
    for taskid_file in "${scriptsdir}"/${processname}_*.${ARRAY_TASKID_FEXT}; do
        if [ -f "${taskid_file}" ]; then
            id=`cat "${taskid_file}"`
            if [ -z "${ids}" ]; then
                ids=$id
            else
                ids="${ids} ${id}"
            fi
        fi
    done

    echo ${ids}
}

########
mark_process_as_dont_execute()
{
    local processname=$1
    local reason=$2

    if [ "${PANPIPE_DONT_EXEC_PROCESSES[${processname}]}" = "" ]; then
        PANPIPE_DONT_EXEC_PROCESSES[${processname}]=${reason}
    else
        local curr_val=PANPIPE_DONT_EXEC_PROCESSES[${processname}]
        PANPIPE_DONT_EXEC_PROCESSES[${processname}]="${curr_val},${reason}"
    fi
}

########
mark_process_as_reexec()
{
    local processname=$1
    local reason=$2

    if [ "${PANPIPE_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        PANPIPE_REEXEC_PROCESSES[${processname}]=${reason}
    else
        local curr_val=PANPIPE_REEXEC_PROCESSES[${processname}]
        PANPIPE_REEXEC_PROCESSES[${processname}]="${curr_val},${reason}"
    fi
}

########
get_reexec_processes_as_string()
{
    local result=""
    for processname in "${!PANPIPE_REEXEC_PROCESSES[@]}"; do
        if [ "${result}" = "" ]; then
            result=${processname}
        else
            result="${result},${processname}"
        fi
    done

    echo ${result}
}

########
process_should_be_reexec()
{
    local processname=$1

    if [ "${PANPIPE_REEXEC_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        if [ "${PANPIPE_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION[${processname}]}" = "" ]; then
            return 0
        else
            return 1
        fi
    fi
}

########
process_should_not_be_exec()
{
    local processname=$1

    if [ "${PANPIPE_DONT_EXEC_PROCESSES[${processname}]}" = "" ]; then
        return 1
    else
        return 0
    fi
}

########
signal_process_completion()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local idx=$3
    local total=$4

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`
    echo "Finished task idx: $idx ; Total: $total" >> "${finished_filename}"
}

########
get_signal_process_completion_cmd()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local total=$3

    # Signal completion
    # NOTE: A file lock is not necessary for the following operation
    # since echo is atomic when writing short lines (for safety, up to
    # 512 bytes, source:
    # https://stackoverflow.com/questions/9926616/is-echo-atomic-when-writing-single-lines/9927415#9927415)
    if [ ${total} -eq 1 ]; then
        echo "echo \"Finished task idx: 1 ; Total: $total\" >> `get_process_finished_filename "${dirname}" ${processname}`"
    else
        echo "echo \"Finished task idx: \${SLURM_ARRAY_TASK_ID} ; Total: $total\" >> `get_process_finished_filename "${dirname}" ${processname}`"
    fi
}

########
display_begin_process_message()
{
    echo "Process started at `date +"%D %T"`" >&2
}

########
display_end_process_message()
{
    echo "Process finished at `date +"%D %T"`" >&2
}
