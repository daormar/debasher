########################################
# SCHEDULER FUNCTIONS RELATED TO SLURM #
########################################

#############
# CONSTANTS #
#############

# PROCESS METHOD NAMES
PROCESS_METHOD_NAME_SLURM_SIGTERM_HANDLER="${PROCESS_METHOD_SEP}slurm_sigterm_handler"

########
get_slurm_version()
{
    if [ "$SBATCH" = "" ]; then
        echo "0"
    else
        "$SBATCH" --version | "$AWK" '{print $2}'
    fi
}

########
slurm_supports_aftercorr_deptype()
{
    local slurm_ver=`get_slurm_version`
    local slurm_ver_num=`version_to_number ${slurm_ver}`
    local slurm_ver_aftercorr_num=`version_to_number ${FIRST_SLURM_VERSION_WITH_AFTERCORR}`
    if [ "${slurm_ver_num}" -ge "${slurm_ver_aftercorr_num}" ]; then
        return 0
    else
        return 1
    fi
}

########
init_slurm_scheduler()
{
    # Verify if aftercorr dependency type is supported by SLURM
    if slurm_supports_aftercorr_deptype; then
        AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM=1
    else
        AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM=0
    fi
}

########
print_script_header_slurm_sched()
{
    get_sigterm_handler_funcname()
    {
        local processname=$1

        echo "${processname}${PROCESS_METHOD_NAME_SLURM_SIGTERM_HANDLER}"
    }

    write_sigterm_handler()
    {
        local funcname=$1
        echo "${funcname} ()"
        echo "{"
        echo " echo \"SIGTERM received: process execution will be aborted\""
        echo " exit 1"
        echo "}"
    }

    local fname=$1
    local dirname=$2
    local processname=$3
    local num_tasks=$4

    local sigterm_handler_funcname=`get_sigterm_handler_funcname "${processname}"`
    if ! func_exists "${sigterm_handler_funcname}"; then
        write_sigterm_handler "${sigterm_handler_funcname}"
    fi
    echo "trap '${sigterm_handler_funcname}' SIGTERM"
    echo "DEBASHER_SCRIPT_FILENAME=\"$(esc_dq "${fname}")\""
    echo "DEBASHER_DIR_NAME=\"$(esc_dq "${dirname}")\""
    echo "DEBASHER_PROCESS_NAME=${processname}"
    echo "DEBASHER_NUM_TASKS=${num_tasks}"
}

########
print_script_body_slurm_sched()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local skip_funct=$3
    local reset_funct=$4
    local funct=$5
    local post_funct=$6
    local opt_array_size=$7
    local opts_fname=$8

    # Retrieve and deserialize process options
    if [ "${opt_array_size}" -gt 1 ]; then
        echo "sargs=\`get_file_opts_for_process_and_task \"${opts_fname}\" \"\${SLURM_ARRAY_TASK_ID}\"\`"
        echo "deserialize_args \"\${sargs}\""
    else
        echo "sargs=\`get_file_opts_for_process_and_task \"${opts_fname}\" 0\`"
        echo "deserialize_args \"\${sargs}\""
    fi

    # Write skip function if it was provided
    if [ "${skip_funct}" != ${FUNCT_NOT_FOUND} ]; then
        echo "${skip_funct} \"\${DESERIALIZED_ARGS[@]}\" && { echo \"Warning: execution of ${processname} will be skipped since the process skip function has finished with exit code \$?\" >&2; exit 1; }"
    fi

    echo "display_begin_process_message"

    # Reset output directory
    if [ "${reset_funct}" = ${FUNCT_NOT_FOUND} ]; then
        if [ "${opt_array_size}" -eq 1 ]; then
            echo "default_reset_outfiles_for_process \"$(esc_dq "${dirname}")\" ${processname}"
        else
            echo "default_reset_outfiles_for_process_array \"$(esc_dq "${dirname}")\" ${processname} ${taskidx}"
        fi
    else
        echo "${reset_funct} \"\${DESERIALIZED_ARGS[@]}\""
    fi

    # Write function to be executed
    echo "${funct} \"\${DESERIALIZED_ARGS[@]}\""
    echo "funct_exit_code=\$?"
    echo "if [ \${funct_exit_code} -ne 0 ]; then echo \"Error: execution of ${funct} failed with exit code \${funct_exit_code}\" >&2; else echo \"Function ${funct} successfully executed\" >&2; fi"

    # Write post function if it was provided
    if [ "${post_funct}" != ${FUNCT_NOT_FOUND} ]; then
        echo "${post_funct} \"\${DESERIALIZED_ARGS[@]}\" || { echo \"Error: execution of ${post_funct} failed with exit code \$?\" >&2; exit 1; }"
    fi

    # Return if function to be executed failed
    echo "if [ \${funct_exit_code} -ne 0 ]; then exit 1; fi"

    # Signal process completion
    local sign_process_completion_cmd=`get_signal_process_completion_cmd "${dirname}" "${processname}" "SLURM_ARRAY_TASK_ID" "${opt_array_size}"`
    echo "${sign_process_completion_cmd} || { echo \"Error: process completion could not be signaled\" >&2; exit 1; }"
}

########
print_script_foot_slurm_sched()
{
    echo "display_end_process_message"
}

########
write_env_vars_and_funcs_slurm()
{
    local dirname=$1

    # Write general environment variables and functions
    write_env_vars_and_funcs "${dirname}"

    # Write slurm sched environment variables
    declare -p SLURM_SCHED_LOG_FEXT
    declare -p SLURM_EXEC_ATTEMPT_FEXT_STRING
    declare -p SRUN

    # Write slurm sched environment functions
    declare -f write_env_vars_and_funcs_slurm
    declare -f seq_execute_slurm
    declare -f get_script_log_filenames_slurm
}

########
create_slurm_script()
{
    # Init variables
    local dirname=$1
    local processname=$2
    local fname=`get_script_filename "${dirname}" ${processname}`
    local skip_funct=`get_skip_funcname ${processname}`
    local reset_funct=`get_reset_funcname ${processname}`
    local funct=`get_exec_funcname ${processname}`
    local post_funct=`get_post_funcname ${processname}`
    local opts_fname=$3
    local opt_array_size=$4

    # Write bash shebang
    local BASH_SHEBANG=`init_bash_shebang_var`
    echo "${BASH_SHEBANG}" > "${fname}" || return 1

    # Write environment variables
    write_env_vars_and_funcs_slurm "${dirname}" | exclude_readonly_vars >> "${fname}" ; pipe_fail || return 1

    # Print header
    print_script_header_slurm_sched "${fname}" "${dirname}" "${processname}" "${opt_array_size}" >> "${fname}" || return 1

    # Print body
    print_script_body_slurm_sched "${dirname}" "${processname}" "${skip_funct}" "${reset_funct}" "${funct}" "${post_funct}" "${opt_array_size}" "${opts_fname}" >> "${fname}" || return 1

    # Print foot
    print_script_foot_slurm_sched >> "${fname}" || return 1

    # Give execution permission
    chmod u+x "${fname}" || return 1
}

########
get_slurm_attempt_suffix()
{
    local attempt_no=$1

    if [ ${attempt_no} -eq 1 ]; then
        echo ""
    else
        echo "${SLURM_EXEC_ATTEMPT_FEXT_STRING}${attempt_no}"
    fi
}

########
get_slurm_jobname()
{
    local processname=$1
    local attempt_no=$2
    local attempt_suffix=`get_slurm_attempt_suffix ${attempt_no}`

    echo ${processname}${attempt_suffix}
}

########
get_slurm_output()
{
    local dirname=$1
    local processname=$2
    local array_size=$3
    local attempt_no=$4
    local attempt_suffix=`get_slurm_attempt_suffix ${attempt_no}`

    if [ ${array_size} -eq 1 ]; then
        local slurm_log_filename=`get_process_log_filename_slurm "${dirname}" ${processname}`
        echo ${slurm_log_filename}${attempt_suffix}
    else
        local slurm_task_template_log_filename=`get_task_template_log_filename_slurm "${dirname}" ${processname}`
        echo ${slurm_task_template_log_filename}${attempt_suffix}
    fi
}

########
get_slurm_cpus_opt()
{
    local cpus=$1

    if [ "${cpus}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--cpus-per-task=${cpus}"
    fi
}

########
get_slurm_mem_opt()
{
    local mem=$1

    if [ "${mem}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--mem=${mem}"
    fi
}

########
get_slurm_time_opt()
{
    local time=$1

    if [ "${time}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--time=${time}"
    fi
}

########
get_slurm_account_opt()
{
    local account=$1

    if [ "${account}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "-A ${account}"
    fi
}

########
get_slurm_nodes_opt()
{
    local nodes=$1

    if [ "${nodes}" = ${ATTR_NOT_FOUND} ]; then
        if [ "${DEBASHER_DEFAULT_NODES}" != "" ]; then
            echo "-w ${DEBASHER_DEFAULT_NODES}"
        else
            echo ""
        fi
    else
        echo "-w ${nodes}"
    fi
}

########
get_slurm_partition_opt()
{
    local partition=$1

    if [ "${partition}" = ${ATTR_NOT_FOUND} ]; then
        echo ""
    else
        echo "--partition=${partition}"
    fi
}

########
get_slurm_dependency_opt()
{
    local processdeps=$1

    # Create dependency option
    if [ "${processdeps}" = ${ATTR_NOT_FOUND} -o "${processdeps}" = "" ]; then
        echo ""
    else
        echo "--dependency=${processdeps}"
    fi
}

########
get_slurm_task_array_opt()
{
    local file=$1
    local task_array_list=$2
    local throttle=$3

    if [ ${throttle} -eq ${DEBASHER_ARRAY_TASK_NOTHROTTLE} ]; then
        echo "--array=${task_array_list}"
    else
        echo "--array=${task_array_list}%${throttle}"
    fi
}

########
set_slurm_jobcorr_like_deps_for_listitem()
{
    local specified_jids=$1
    local jid=$2
    local deptype=$3
    local additional_deps=$4
    local listitem=$5

    # Extract specified jids
    local sep=","
    local spec_jid_array
    IFS="$sep" read -r -a spec_jid_array <<< "${specified_jids}"

    # Extract start and end indices
    local sep="-"
    local idx_array
    IFS="$sep" read -r -a idx_array <<< "${listitem}"
    local start=${idx_array[0]}
    if [ ${#idx_array[@]} -eq 1 ]; then
        local end=${idx_array[0]}
    else
        local end=${idx_array[1]}
    fi

    # Process indices
    local idx=${start}
    while [ ${idx} -le ${end} ]; do
        # Obtain dependencies
        local dependencies=${additional_deps}
        for specified_jid in ${spec_jid_array[@]}; do
            if [ "${dependencies}" = "" ]; then
                dependencies=${deptype}:${specified_jid}_${idx}
            else
                dependencies=${dependencies},${deptype}:${specified_jid}_${idx}
            fi
        done
        # Update dependencies
        "${SCONTROL}" update jobid=${jid}_${idx} Dependency=${dependencies} || return 1
        # Increase task index
        idx=$(( idx + 1 ))
    done
}

########
set_slurm_jobcorr_like_deps()
{
    local specified_jids=$1
    local jid=$2
    local array_size=$3
    local task_array_list=$4
    local deptype=$5
    local additional_deps=$6

    # Iterate over task array list items
    local sep=","
    local array
    IFS="$sep" read -r -a array <<< "${task_array_list}"
    local listitem
    for listitem in ${array[@]}; do
        set_slurm_jobcorr_like_deps_for_listitem ${specified_jids} ${jid} ${deptype} "${additional_deps}" ${listitem} || return 1
    done
}

########
combine_slurm_deps()
{
    local deps1=$1
    local deps2=$2

    if [ "${deps1}" = "" ]; then
        echo $deps2
    else
        if [ "${deps2}" = "" ]; then
            echo $deps1
        else
            echo ${deps1},${deps2}
        fi
    fi
}

########
slurm_get_attempt_deps()
{
    # Initialize variables
    local attempt_jids=$1
    local attempt_deps

    # Iterate of attempt jids
    local attempt_jids_blanks=`replace_str_elem_sep_with_blank "," ${attempt_jids}`
    local attempt_jid
    for attempt_jid in ${attempt_jids_blanks}; do
        if [ "${attempt_deps}" = "" ]; then
            attempt_deps="${AFTERNOTOK_PROCESSDEP_TYPE}:${attempt_jid}"
        else
            attempt_deps="${attempt_deps},${AFTERNOTOK_PROCESSDEP_TYPE}:${attempt_jid}"
        fi
    done

    echo ${attempt_deps}
}

########
slurm_launch_attempt()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local attempt_no=$6
    local processdeps=$7
    local prev_attempt_jids=$8
    local mem_attempt=$9
    local time_attempt=${10}

    # Obtain augmented dependencies
    local attempt_deps=`slurm_get_attempt_deps ${prev_attempt_jids}`
    local augmented_deps=`combine_slurm_deps ${processdeps} ${attempt_deps}`

    # Retrieve specification
    local cpus=`extract_attr_from_process_spec "$process_spec" "cpus"`
    local account=`extract_attr_from_process_spec "$process_spec" "account"`
    local partition=`extract_attr_from_process_spec "$process_spec" "partition"`
    local nodes=`extract_attr_from_process_spec "$process_spec" "nodes"`
    local spec_throttle=`extract_attr_from_process_spec "$process_spec" "throttle"`
    local sched_throttle=`get_scheduler_throttle ${spec_throttle}`

    # Define options for sbatch
    local jobname=`get_slurm_jobname $processname $attempt_no`
    local output=`get_slurm_output "$dirname" $processname $array_size $attempt_no`
    local cpus_opt=`get_slurm_cpus_opt ${cpus}`
    local mem_opt=`get_slurm_mem_opt ${mem_attempt}`
    local time_opt=`get_slurm_time_opt ${time_attempt}`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${augmented_deps}"`
    if [ ${array_size} -gt 1 ]; then
        local jobarray_opt=`get_slurm_task_array_opt ${file} ${task_array_list} ${sched_throttle}`
    fi

    # Submit job (initially it is put on hold)
    local jid
    jid=$("$SBATCH" --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} --job-name ${jobname} --output ${output} --kill-on-invalid-dep=yes --signal=B:SIGTERM@10 -H "${file}")
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        local command="$SBATCH --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} -H ${file}"
        echo "Error while launching attempt job for process ${processname} (${command})" >&2
        return 1
    fi

    # Update dependencies when executing job arrays for second or
    # further attempts
    if [ ${array_size} -gt 1 -a ${attempt_no} -ge 2 ]; then
        local deptype="${AFTERNOTOK_PROCESSDEP_TYPE}"
        set_slurm_jobcorr_like_deps ${prev_attempt_jids} ${jid} ${array_size} ${task_array_list} ${deptype} "${processdeps}" || { return 1 ; echo "Error while launching attempt job for process ${processname} (set_slurm_jobcorr_like_deps)" >&2; }
    fi

    # Release job
    $("$SCONTROL" release $jid)
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        local command="$SCONTROL release $jid"
        echo "Error while launching attempt job for process ${processname} (${command})" >&2
        return 1
    fi

    echo $jid
}

########
slurm_launch_preverif_job()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local attempt_jids=$6

    # Obtain dependencies for attempts
    local attempt_deps=`slurm_get_attempt_deps ${attempt_jids}`

    # Retrieve specification
    local account=`extract_attr_from_process_spec "$process_spec" "account"`
    local partition=`extract_attr_from_process_spec "$process_spec" "partition"`
    local nodes=`extract_attr_from_process_spec "$process_spec" "nodes"`

    # Define options
    local jobname="${processname}__preverif"
    local preverif_logf=`get_process_log_preverif_filename_slurm "${dirname}" ${processname}`
    local cpus_opt=`get_slurm_cpus_opt 1`
    local mem_opt=`get_slurm_mem_opt 16`
    local time_opt=`get_slurm_time_opt 00:01:00`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local dependency_opt=`get_slurm_dependency_opt "${attempt_deps}"`
    if [ ${array_size} -gt 1 ]; then
        local jobarray_opt=`get_slurm_task_array_opt ${file} ${task_array_list} ${DEBASHER_ARRAY_TASK_NOTHROTTLE}`
    fi

    # Submit preliminary verification job (the job will fail if all
    # attempts fail, initially it is put on hold)
    local jid
    jid=$("$SBATCH" --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} --job-name ${jobname} --output ${preverif_logf} --kill-on-invalid-dep=yes -H --wrap "true")
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        echo "Error while launching preliminary verification job for process ${processname}" >&2
        return 1
    fi

    # Update dependencies when executing job arrays
    if [ ${array_size} -gt 1 ]; then
        local deptype="${AFTERNOTOK_PROCESSDEP_TYPE}"
        local additional_deps=""
        set_slurm_jobcorr_like_deps ${attempt_jids} ${jid} ${array_size} ${task_array_list} ${deptype} "${additional_deps}" || { return 1 ; echo "Error while launching preliminary verification job for process ${processname} (set_slurm_jobcorr_like_deps)" >&2; }
    fi

    # Release job
    $("$SCONTROL" release $jid)
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        local command="$SCONTROL release $jid"
        echo "Error while launching attempt job for process ${processname} (${command})" >&2
        return 1
    fi

    echo $jid
}

########
slurm_launch_verif_job()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local preverif_jid=$6

    # Retrieve specification
    local account=`extract_attr_from_process_spec "$process_spec" "account"`
    local partition=`extract_attr_from_process_spec "$process_spec" "partition"`
    local nodes=`extract_attr_from_process_spec "$process_spec" "nodes"`

    # Define options
    local jobname="${processname}__verif"
    local verif_logf=`get_process_log_verif_filename_slurm "${dirname}" ${processname}`
    local cpus_opt=`get_slurm_cpus_opt 1`
    local mem_opt=`get_slurm_mem_opt 16`
    local time_opt=`get_slurm_time_opt 00:01:00`
    local account_opt=`get_slurm_account_opt ${account}`
    local nodes_opt=`get_slurm_nodes_opt ${nodes}`
    local partition_opt=`get_slurm_partition_opt ${partition}`
    local verjob_deps="${AFTERNOTOK_PROCESSDEP_TYPE}:${preverif_jid}"
    local dependency_opt=`get_slurm_dependency_opt "${verjob_deps}"`
    if [ ${array_size} -gt 1 ]; then
        local jobarray_opt=`get_slurm_task_array_opt ${file} ${task_array_list} ${DEBASHER_ARRAY_TASK_NOTHROTTLE}`
    fi

    # Submit verification job (the job will succeed if preliminary
    # verification job fails, initially it is put on hold)
    local jid
    jid=$("$SBATCH" --parsable ${cpus_opt} ${mem_opt} ${time_opt} ${account_opt} ${partition_opt} ${nodes_opt} ${dependency_opt} ${jobarray_opt} --job-name ${jobname} --output ${verif_logf} --kill-on-invalid-dep=yes -H --wrap "true")
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        echo "Error while launching verification job for process ${processname}" >&2
        return 1
    fi

    # Update dependencies when executing job arrays
    if [ ${array_size} -gt 1 ]; then
        local deptype="${AFTERNOTOK_PROCESSDEP_TYPE}"
        local additional_deps=""
        set_slurm_jobcorr_like_deps ${preverif_jid} ${jid} ${array_size} ${task_array_list} ${deptype} "${additional_deps}" || { return 1 ; echo "Error while launching verification job for process ${processname} (set_slurm_jobcorr_like_deps)" >&2; }
    fi

    # Release job
    $("$SCONTROL" release $jid)
    local exit_code=$?

    # Check for errors
    if [ ${exit_code} -ne 0 ]; then
        local command="$SCONTROL release $jid"
        echo "Error while launching attempt job for process ${processname} (${command})" >&2
        return 1
    fi

    echo $jid
}

########
slurm_launch()
{
    # Initialize variables
    local dirname=$1
    local processname=$2
    local file=`get_script_filename "${dirname}" ${processname}`
    local array_size=$3
    local task_array_list=$4
    local process_spec=$5
    local processdeps=$6
    local outvar=$7

    # Launch execution attempts
    local attempt_no=0
    local attempt_jids=""
    local mem=`extract_attr_from_process_spec "$process_spec" "mem"`
    local time=`extract_attr_from_process_spec "$process_spec" "time"`
    local num_attempts=`get_num_attempts ${time} ${mem}`
    local attempt_no=1

    while [ ${attempt_no} -le ${num_attempts} ]; do
        # Obtain attempt-dependent parameters
        local mem_attempt=`get_mem_attempt_value ${mem} ${attempt_no}`
        local time_attempt=`get_time_attempt_value ${time} ${attempt_no}`

        # Launch attempt
        jid=`slurm_launch_attempt "${dirname}" ${processname} ${array_size} ${task_array_list} "${process_spec}" ${attempt_no} "${processdeps}" "${attempt_jids}" ${mem_attempt} ${time_attempt}` || return 1

        # Update variable storing jids of previous attempts (after
        # launching all attempts this variable is also useful to launch
        # pre-verification job)
        if [ "${attempt_jids}" = "" ]; then
            attempt_jids=${jid}
        else
            attempt_jids="${attempt_jids},${jid}"
        fi

        attempt_no=$(( attempt_no + 1 ))
    done

    # If more than one attempt was requested, verify if any of the
    # attempts were successful (currently, verification requires to
    # launch two jobs)
    if [ ${num_attempts} -gt 1 ]; then
        preverif_jid=`slurm_launch_preverif_job "${dirname}" ${processname} ${array_size} ${task_array_list} "${process_spec}" ${attempt_jids}` || return 1
        verif_jid=`slurm_launch_verif_job "${dirname}" ${processname} ${array_size} ${task_array_list} "${process_spec}" ${preverif_jid}` || return 1
        # Set output value
        eval "${outvar}='${attempt_jids},${preverif_jid},${verif_jid}'"
    else
        eval "${outvar}='${jid}'"
    fi
}

########
get_primary_id_slurm()
{
    local launch_id_info=$1
    local str_array
    local sep=","
    IFS="$sep" read -r -a str_array <<< "${launch_id_info}"

    local array_len=${#str_array[@]}
    if [ ${array_len} -eq 1 ]; then
        # launch_id_info has 1 id, so only one attempt was executed
        echo ${str_array[0]}
    else
        # launch_id_info has more than 1 id, so multiple attempts were
        # executed. In this case, the global id is returned as the
        # primary one
        local last_array_idx=$(( array_len - 1 ))
        echo ${str_array[${last_array_idx}]}
    fi
}

########
get_global_id_slurm()
{
    # Initialize variables
    local launch_id_info=$1
    local str_array
    local sep=","
    IFS="$sep" read -r -a str_array <<< "${launch_id_info}"

    # Return last id stored in launch output variable, which corresponds
    # to the global id
    local array_len=${#str_array[@]}
    local last_array_idx=$(( array_len - 1 ))
    echo ${str_array[${last_array_idx}]}
}

########
get_slurm_state_code()
{
    local jid=$1
    "${SQUEUE}" -j $jid -h -o "%t" 2>/dev/null
}

########
slurm_jid_exists()
{
    local jid=$1

    # Use squeue to get job status
    local squeue_success=1
    "${SQUEUE}" -j $jid > /dev/null 2>&1 || squeue_success=0

    if [ ${squeue_success} -eq 1 ]; then
        # If squeue succeeds, determine if it returns a state code
        local job_state_code=`get_slurm_state_code $jid`
        if [ -z "${job_state_code}" ]; then
            return 1
        else
            return 0
        fi
    else
        # Since squeue has failed, the job is not being executed
        return 1
    fi
}

########
slurm_stop_jid()
{
    local jid=$1

    "${SCANCEL}" $jid  > /dev/null 2>&1 || return 1

    return 0
}

########
map_deptype_if_necessary_slurm()
{
    local deptype=$1
    case $deptype in
        ${AFTERCORR_PROCESSDEP_TYPE})
            if [ ${AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM} -eq 1 ]; then
                echo ${deptype}
            else
                echo ${AFTEROK_PROCESSDEP_TYPE}
            fi
            ;;
        *)
            echo $deptype
            ;;
    esac
}

########
get_process_log_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`

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
    scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.preverif.${SLURM_SCHED_LOG_FEXT}"
}

########
get_process_log_verif_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.verif.${SLURM_SCHED_LOG_FEXT}"
}

########
get_process_log_signcomp_filename_slurm()
{
    local dirname=$1
    local processname=$2

    # Get scripts dir
    scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`

    echo "${scriptsdir}/${processname}.signcomp.${SLURM_SCHED_LOG_FEXT}"
}

########
get_task_log_filename_slurm()
{
    local scriptsdir=$1
    local processname=$2
    local taskidx=$3

    echo "${scriptsdir}/${processname}_${taskidx}.${SLURM_SCHED_LOG_FEXT}"
}

########
get_task_last_attempt_logf_slurm()
{
    local dirname=$1
    local processname=$2
    local taskidx=$3

    # Get scripts dir
    local scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`

    # Obtain number of log files
    local logfname=`get_task_log_filename_slurm "$scriptsdir" "$processname" "$taskidx"`
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
clean_process_files_slurm()
{
    clean_process_id_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local processid_file=`get_processid_filename "${dirname}" ${processname}`
        "${RM}" -f "${processid_file}"
    }

    clean_process_id_files_array()
    {
        local scriptsdir=$1
        local processname=$2
        local idx=$3

        local array_taskid_file=`get_array_taskid_filename "${scriptsdir}" ${processname} ${idx}`
        if [ -f "${array_taskid_file}" ]; then
            "${RM}" "${array_taskid_file}"
        fi
    }

    clean_process_log_files_non_array()
    {
        local dirname=$1
        local processname=$2

        local slurm_log_filename=`get_process_log_filename_slurm "${dirname}" ${processname}`
        "${RM}" -f "${slurm_log_filename}*"
        local slurm_log_preverif=`get_process_log_preverif_filename_slurm "${dirname}" ${processname}`
        "${RM}" -f "${slurm_log_preverif}"
        local slurm_log_verif=`get_process_log_verif_filename_slurm "${dirname}" ${processname}`
        "${RM}" -f "${slurm_log_verif}"
        local slurm_log_signcomp=`get_process_log_signcomp_filename_slurm "${dirname}" ${processname}`
        "${RM}" -f "${slurm_log_signcomp}"
    }

    clean_process_log_files_array()
    {
        local scriptsdir=$1
        local processname=$2
        local idx=$3

        local slurm_task_log_filename=`get_task_log_filename_slurm "${scriptsdir}" "${processname}" "${idx}"`
        if [ -f "${slurm_task_log_filename}" ]; then
            "${RM}" "${slurm_task_log_filename}"
        fi
    }

    local dirname=$1
    local processname=$2
    local array_size=$3
    # Remove log files depending on array size
    if [ ${array_size} -eq 1 ]; then
        clean_process_id_files_non_array "${dirname}" "${processname}"
        clean_process_log_files_non_array "${dirname}" "${processname}"
    else
        # If array size is greater than 1, remove only those log files
        # related to unfinished array tasks
        local pending_tasks=`get_list_of_pending_tasks_in_array "${dirname}" ${processname} ${array_size}`
        if [ "${pending_tasks}" != "" ]; then
            # Store string of pending tasks into an array
            local pending_tasks_array
            IFS=',' read -ra pending_tasks_array <<< "${pending_tasks}"

            # Iterate over pending tasks
            local scriptsdir=`get_prg_scripts_dir_for_process "${dirname}" "${processname}"`
            local idx
            for idx in "${pending_tasks_array[@]}"; do
                clean_process_id_files_array "${scriptsdir}" "${processname}" "${idx}"
                clean_process_log_files_array "${scriptsdir}" "${processname}" "${idx}"
            done
        fi
    fi
}

########
slurm_stop_process()
{
    # Initialize variables
    local ids_info=$1

    # Process ids information for process (each element in ids_info is an
    # individual jid or a comma-separated list of them)
    for jid_list in ${ids_info}; do
        # Process comma separated list of job ids
        local separator=","
        local jid_list_blanks=`replace_str_elem_sep_with_blank "${separator}" ${jid_list}`
        for jid in ${jid_list_blanks}; do
            slurm_stop_jid $jid || { echo "Error while stopping job with id $jid" >&2 ; return 1; }
        done
    done
}

########
get_elapsed_time_for_process_slurm()
{
    local dirname=$1
    local processname=$2

    # Obtain finished filename
    local finished_filename=`get_process_finished_filename "${dirname}" ${processname}`

    if [ -f "${finished_filename}" ]; then
        # Get number of array tasks
        local num_tasks=`get_num_array_tasks_from_finished_file "${finished_filename}"`

        case $num_tasks in
            0)  echo ${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
                ;;
            1)  # Process is not a task array
                log_filename=`get_process_last_attempt_logf_slurm "${dirname}" ${processname}`
                local difft=`get_elapsed_time_from_logfile "${log_filename}"`
                echo ${difft}
               ;;
            *)  # Process is a task array
                local result=""
                local taskidx
                local sum_difft=0
                for taskidx in `get_finished_array_task_indices "${dirname}" ${processname}`; do
                    local log_filename=`get_task_last_attempt_logf_slurm "${dirname}" ${processname} ${taskidx}`
                    local difft=`get_elapsed_time_from_logfile "${log_filename}"`
                    sum_difft=$((sum_difft + difft))
                    if [ ! -z "${result}" ]; then
                        result="${result} "
                    fi
                    result="${result}${taskidx}->${difft} ;"
                done
                result="${sum_difft} : ${result}"
                echo ${result}
                ;;
        esac
    else
        echo ${UNKNOWN_ELAPSED_TIME_FOR_PROCESS}
    fi
}

########
get_script_log_filenames_slurm()
{
    local scripts_dirname=$1

    find "${scripts_dirname}" -name "*.${SLURM_SCHED_LOG_FEXT}" -exec echo {} \;
}

########
seq_execute_slurm()
{
    create_seq_execute_script()
    {
        local dirname=$1
        local process_to_launch=$2
        local fname=$3

        # Write bash shebang
        local BASH_SHEBANG=`init_bash_shebang_var`
        echo "${BASH_SHEBANG}" > "${fname}" || return 1

        # Write environment variables
        write_env_vars_and_funcs_slurm "${dirname}" | exclude_readonly_vars >> "${fname}" ; pipe_fail || return 1

        # Add call to process function
        echo "${process_to_launch} \"\$@\"" >> "${fname}" || return 1

        # Give execution permission
        chmod u+x "${fname}" || return 1
    }

    local process_to_launch=$1

    # Obtain template for tmp file
    local tmpfile_templ
    tmpfile_templ="${FUNCNAME[0]}_${process_to_launch}.XXXXXX"

    # Obtain file name
    local script_name
    script_name=`"${MKTEMP}" -t "${tmpfile_templ}"` || return 1

    # Create script
    create_seq_execute_script "${PROGRAM_OUTDIR}" "${process_to_launch}" "${script_name}" || return 1

    # Launch script
    shift
    "${SRUN}" "${script_name}" "$@" || return 1

    # Clean temporary files on exit
    "${RM}" "${script_name}"
}
