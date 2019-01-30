# *- bash -*

#############
# CONSTANTS #
#############

###################################
# PIPELINE SOFTWARE TESTING STEPS #
###################################

########
step_a_explain_cmdline_opts()
{
    :
}

########
step_a_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local jobspec=$2
    local optlist=""
    
    # Define the -step-outd option, the output directory for the step,
    # which will have the same name of the step
    define_default_step_outd_opt "$cmdline" "$jobspec" optlist || exit 1

    # Save option list
    save_opt_list optlist
}

########
step_a()
{
    display_begin_step_message

    # Initialize variables
    local step_outd=`read_opt_value_from_line "$*" "-step-outd"`

    # sleep some time
    sleep 10

    display_end_step_message
}

########
step_b_explain_cmdline_opts()
{
    :
}

########
step_b_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local jobspec=$2
    local optlist=""
    
    # Define the -step-outd option, the output directory for the step,
    # which will have the same name of the step
    define_default_step_outd_opt "$cmdline" "$jobspec" optlist || exit 1

    # Save option list
    save_opt_list optlist
}

########
step_b()
{
    display_begin_step_message

    # Initialize variables
    local step_outd=`read_opt_value_from_line "$*" "-step-outd"`

    # sleep some time
    sleep 10

    display_end_step_message
}

########
step_c_explain_cmdline_opts()
{
    :
}

########
step_c_define_opts()
{
    # Initialize variables
    local cmdline=$1
    local jobspec=$2
    local basic_optlist=""
    
    # Define the -step-outd option, the output directory for the step,
    # which will have the same name of the step
    define_default_step_outd_opt "$cmdline" "$jobspec" basic_optlist || exit 1

    # Save option list twice (step will be executed two times)
    for id in 1 2; do
        local optlist=${basic_optlist}
        define_opt "-id" $id optlist || exit 1
        save_opt_list optlist
    done
}

########
step_c()
{
    display_begin_step_message

    # Initialize variables
    local step_outd=`read_opt_value_from_line "$*" "-step-outd"`
    local id=`read_opt_value_from_line "$*" "-id"`

    # sleep some time
    sleep 10

    # create file
    touch ${step_outd}/$id
    
    display_end_step_message
}
