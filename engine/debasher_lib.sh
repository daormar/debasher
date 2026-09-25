# DeBasher package
# Copyright (C) 2019-2026 Daniel Ortiz-Mart\'inez
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

#############
# CONSTANTS #
#############

# STRING HANDLING
DEBASHER_NOFILE="_NONE_"
DEBASHER_ATTR_NOT_FOUND="_ATTR_NOT_FOUND_"
DEBASHER_OPT_NOT_FOUND="_OPT_NOT_FOUND_"
DEBASHER_DEP_NOT_FOUND="_DEP_NOT_FOUND_"
DEBASHER_FUNCT_NOT_FOUND="_FUNCT_NOT_FOUND_"
DEBASHER_VAR_NOT_FOUND="_VAR_NOT_FOUND_"
DEBASHER_VOID_VALUE="_VOID_VALUE_"
DEBASHER_GENERAL_OPT_CATEGORY="GENERAL"
DEBASHER_SPACE_SUBSTITUTE="__SPACE_SUBSTITUTE__"
DEBASHER_ARG_SEP="<_ARG_SEP_>"
DEBASHER_ARRAY_TASK_SEP=" ||| "
DEBASHER_PROCESSDEPS_SPEC="processdeps"
DEBASHER_ATTEMPT_SEP=","
DEBASHER_PROCESS_PLUS_DEPTYPE_SEP=":"
DEBASHER_PROCESSDEPS_SEP_COMMA=","
DEBASHER_PROCESSDEPS_SEP_INTERR="?"
DEBASHER_ASSOC_ARRAY_ELEM_SEP="__ELEMSEP__"
DEBASHER_ASSOC_ARRAY_KEY_LEN="__LEN__"
DEBASHER_ASSOC_ARRAY_PROC_SEP="__PROCSEP__"
DEBASHER_OPT_MULTIVAL_SEP="__OPTMULTIVALSEP__"
DEBASHER_PROCESSNAME_NS_SEP_MANGLED="__NSSEP__"
DEBASHER_MOD_DIR_SEP=":"
DEBASHER_UI_PROGRAM_DIRNAME=".debasher"
DEBASHER_UI_PROGRAM_METADATA_FNAME="program.json"
DEBASHER_YML_DIR_SEP=":"
DEBASHER_PROCESS_METHOD_SEP="_"
DEBASHER_MODULE_METHOD_SEP="_"
DEBASHER_BEGIN_OF_ADDITIONAL_PROCSPECS_SEP="|||"
DEBASHER_LEGACY_PROCSPECS_SEP=" "
DEBASHER_PROCSPECS_SEP=";"
# Computational specifications that only a resident program reads (see
# _PortWorker._apply_comp_specs): limits of a node, the heartbeat timeout of
# a Supervisor, the startup deadline of a node, or of every node for a
# Supervisor, and the batch runs a launcher node runs at a time, given per
# process with add_debasher_process. Each, when given, is a positive number.
DEBASHER_RESIDENT_COMP_SPEC_NAMES="input_log_max_mb out_backlog_max_mb out_backlog_fail_mb gil_switch_interval_ms heartbeat_timeout_s startup_timeout_s max_concurrent_runs"
# The scheduler with which a launcher node runs its batch runs, one of those
# debasher_exec takes in --sched; the built-in one when not given
DEBASHER_BATCH_SCHED_COMP_SPEC_NAME="batch_sched"
DEBASHER_VALUE_DESCRIPTOR_NAME_PREFIX=".__VAL_DESCRIPTOR__"
DEBASHER_PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX="__PROC_OUT_OPT_DESCRIPTOR__"
DEBASHER_SCHED_OPTS_DIRNAME=".sched_opts"
DEBASHER_SCHED_OPTS_FNAME_FOR_PROCESS_PREFIX="sched_opts_"
DEBASHER_SHDIR_MODULE_OWNER="__SHDIR_MODULE_OWNER__"
DEBASHER_OPTLIST_VARNAME_SUFFIX="optlist"
DEBASHER_DEBASHER_LIB_NAMESPACE="debasher"

# PROCESS TYPES
DEBASHER_REGULAR_PROCESS_TYPE=1
DEBASHER_HEREDOC_PROCESS_TYPE=2
DEBASHER_ALIAS_PROCESS_TYPE=3
DEBASHER_EXT_ALIAS_PROCESS_TYPE=4

# HEREDOC PROCESSES RELATED VARIABLES
#
# Two suffixes exist per language: the "VARNAME" one names the legacy
# variable form (kept unchanged for backwards compatibility, e.g. as
# shown in the DeBasher paper's supplementary material); the
# "FUNCNAME" one names the newer, preferred function form, which
# supports namespaced process names. The function form uses a longer,
# more specific suffix since, unlike the variable one, it was also
# folded into DEBASHER_PROCESS_METHODS (see below) and a short generic
# word like "py" would be too easy to collide with by accident.
DEBASHER_PY_VARNAME_SUFFIX="py"
DEBASHER_PY_FUNCNAME_SUFFIX="heredoc_py"
DEBASHER_PY_END_OF_OPTIONS_MARKER=""
DEBASHER_R_VARNAME_SUFFIX="r"
DEBASHER_R_FUNCNAME_SUFFIX="heredoc_r"
DEBASHER_R_END_OF_OPTIONS_MARKER="--"
DEBASHER_PL_VARNAME_SUFFIX="perl"
DEBASHER_PL_FUNCNAME_SUFFIX="heredoc_perl"
DEBASHER_PL_END_OF_OPTIONS_MARKER="--"
DEBASHER_GROOVY_VARNAME_SUFFIX="groovy"
DEBASHER_GROOVY_FUNCNAME_SUFFIX="heredoc_groovy"
DEBASHER_GROOVY_END_OF_OPTIONS_MARKER="--"
DEBASHER_HEREDOC_LANGUAGES=(python r perl groovy)
DEBASHER_HEREDOC_EOP_MARKERS=(
    "${DEBASHER_PY_END_OF_OPTIONS_MARKER}"
    "${DEBASHER_R_END_OF_OPTIONS_MARKER}"
    "${DEBASHER_PL_END_OF_OPTIONS_MARKER}"
    "${DEBASHER_GROOVY_END_OF_OPTIONS_MARKER}"
)
DEBASHER_HEREDOC_INTERPRETERS=(
    "${PYTHON}"
    "${RSCRIPT}"
    "${PERL}"
    "${GROOVY}"
)
DEBASHER_HEREDOC_INTERPRETER_OPTS=(
    "-c"
    "-e"
    "-e"
    "-e"
)

# INVALID IDENTIFIERS
DEBASHER_INVALID_SID="_INVALID_SID_"
DEBASHER_INVALID_JID="_INVALID_JID_"
DEBASHER_INVALID_PID="_INVALID_PID_"
DEBASHER_INVALID_ARRAY_TID="_INVALID_ARRAY_TID_"

# PROCESS STATUSES AND EXIT CODES
DEBASHER_FINISHED_PROCESS_STATUS="FINISHED"
DEBASHER_FINISHED_PROCESS_EXIT_CODE=0
DEBASHER_INPROGRESS_PROCESS_STATUS="IN-PROGRESS"
DEBASHER_INPROGRESS_PROCESS_EXIT_CODE=1
DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS="UNFINISHED_BUT_RUNNABLE"
DEBASHER_UNFINISHED_BUT_RUNNABLE_PROCESS_EXIT_CODE=2
DEBASHER_UNFINISHED_PROCESS_STATUS="UNFINISHED"
DEBASHER_UNFINISHED_PROCESS_EXIT_CODE=3
DEBASHER_TODO_PROCESS_STATUS="TO-DO"
DEBASHER_TODO_PROCESS_EXIT_CODE=4

# PROCESS METHOD NAMES
DEBASHER_PROCESS_METHOD_NAME_DOCUMENT="${DEBASHER_PROCESS_METHOD_SEP}document"
DEBASHER_PROCESS_METHOD_NAME_RESET_OUTFILES="${DEBASHER_PROCESS_METHOD_SEP}reset_outfiles"
DEBASHER_PROCESS_METHOD_NAME_EXEC=""
DEBASHER_PROCESS_METHOD_NAME_POST="${DEBASHER_PROCESS_METHOD_SEP}post"
DEBASHER_PROCESS_METHOD_NAME_OUTDIR="${DEBASHER_PROCESS_METHOD_SEP}outdir_basename"
DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS="${DEBASHER_PROCESS_METHOD_SEP}explain_cmdline_opts"
DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS="${DEBASHER_PROCESS_METHOD_SEP}explain_opts"
DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS="${DEBASHER_PROCESS_METHOD_SEP}identify_cmdline_opts"
DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS="${DEBASHER_PROCESS_METHOD_SEP}define_opts"
DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPT_DEPS="${DEBASHER_PROCESS_METHOD_SEP}define_opt_deps"
DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE="${DEBASHER_PROCESS_METHOD_SEP}generate_opts_size"
DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS="${DEBASHER_PROCESS_METHOD_SEP}generate_opts"
DEBASHER_PROCESS_METHOD_NAME_SKIP="${DEBASHER_PROCESS_METHOD_SEP}skip"
DEBASHER_PROCESS_METHOD_NAME_CONDA_ENVS="${DEBASHER_PROCESS_METHOD_SEP}conda_envs"
DEBASHER_PROCESS_METHOD_NAME_DOCKER_IMGS="${DEBASHER_PROCESS_METHOD_SEP}docker_imgs"

# ARRAY OF ALL PROCESS METHOD NAMES
DEBASHER_PROCESS_METHODS=(
    "${DEBASHER_PROCESS_METHOD_NAME_DOCUMENT}"
    "${DEBASHER_PROCESS_METHOD_NAME_RESET_OUTFILES}"
    "${DEBASHER_PROCESS_METHOD_NAME_EXEC}"
    "${DEBASHER_PROCESS_METHOD_NAME_POST}"
    "${DEBASHER_PROCESS_METHOD_NAME_OUTDIR}"
    "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS}"
    "${DEBASHER_PROCESS_METHOD_NAME_EXPLAIN_OPTS}"
    "${DEBASHER_PROCESS_METHOD_NAME_IDENTIFY_CMDLINE_OPTS}"
    "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPTS}"
    "${DEBASHER_PROCESS_METHOD_NAME_DEFINE_OPT_DEPS}"
    "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE}"
    "${DEBASHER_PROCESS_METHOD_NAME_GENERATE_OPTS}"
    "${DEBASHER_PROCESS_METHOD_NAME_SKIP}"
    "${DEBASHER_PROCESS_METHOD_NAME_CONDA_ENVS}"
    "${DEBASHER_PROCESS_METHOD_NAME_DOCKER_IMGS}"
)

# PROCESS VAR NAMES (legacy HEREDOC variable form)
DEBASHER_PROCESS_VARNAME_PYEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_PY_VARNAME_SUFFIX}"
DEBASHER_PROCESS_VARNAME_REXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_R_VARNAME_SUFFIX}"
DEBASHER_PROCESS_VARNAME_PERLEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_PL_VARNAME_SUFFIX}"
DEBASHER_PROCESS_VARNAME_GROOVYEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_GROOVY_VARNAME_SUFFIX}"

# ARRAY OF ALL PROCESS VAR NAMES (index-aligned with
# DEBASHER_HEREDOC_LANGUAGES/DEBASHER_PROCESS_FUNCNAMES)
DEBASHER_PROCESS_VARNAMES=(
    "${DEBASHER_PROCESS_VARNAME_PYEXEC}"
    "${DEBASHER_PROCESS_VARNAME_REXEC}"
    "${DEBASHER_PROCESS_VARNAME_PERLEXEC}"
    "${DEBASHER_PROCESS_VARNAME_GROOVYEXEC}"
)

# PROCESS FUNC NAMES (preferred HEREDOC function form)
DEBASHER_PROCESS_FUNCNAME_PYEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_PY_FUNCNAME_SUFFIX}"
DEBASHER_PROCESS_FUNCNAME_REXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_R_FUNCNAME_SUFFIX}"
DEBASHER_PROCESS_FUNCNAME_PERLEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_PL_FUNCNAME_SUFFIX}"
DEBASHER_PROCESS_FUNCNAME_GROOVYEXEC="${DEBASHER_PROCESS_METHOD_SEP}${DEBASHER_GROOVY_FUNCNAME_SUFFIX}"

# ARRAY OF ALL PROCESS FUNC NAMES (index-aligned with
# DEBASHER_HEREDOC_LANGUAGES/DEBASHER_PROCESS_VARNAMES)
DEBASHER_PROCESS_FUNCNAMES=(
    "${DEBASHER_PROCESS_FUNCNAME_PYEXEC}"
    "${DEBASHER_PROCESS_FUNCNAME_REXEC}"
    "${DEBASHER_PROCESS_FUNCNAME_PERLEXEC}"
    "${DEBASHER_PROCESS_FUNCNAME_GROOVYEXEC}"
)

# Both HEREDOC forms are also valid process methods, since a process
# can provide its code through a suffixed function or variable (e.g.
# "_heredoc_py" or, in legacy modules, "_py") looked up the same way
# as any other method.
DEBASHER_PROCESS_METHODS+=("${DEBASHER_PROCESS_FUNCNAMES[@]}" "${DEBASHER_PROCESS_VARNAMES[@]}")

# MODULE METHOD NAMES
DEBASHER_MODULE_METHOD_NAME_DOCUMENT="${DEBASHER_MODULE_METHOD_SEP}document"
DEBASHER_MODULE_METHOD_NAME_SHRDIRS="${DEBASHER_MODULE_METHOD_SEP}shared_dirs"
DEBASHER_MODULE_METHOD_NAME_PROGRAM="${DEBASHER_MODULE_METHOD_SEP}program"
DEBASHER_MODULE_METHOD_NAME_PROGRAM_TYPE="${DEBASHER_MODULE_METHOD_SEP}program_type"

# ARRAY OF ALL MODULE METHOD NAMES
DEBASHER_MODULE_METHODS=(
    "${DEBASHER_MODULE_METHOD_NAME_DOCUMENT}"
    "${DEBASHER_MODULE_METHOD_NAME_SHRDIRS}"
    "${DEBASHER_MODULE_METHOD_NAME_PROGRAM}"
    "${DEBASHER_MODULE_METHOD_NAME_PROGRAM_TYPE}"
)

# PROGRAM TYPES
#
# "general" (default, when a module declares no `_program_type` method)
# is today's one-shot, DAG-scheduled program. "resident" is the new
# long-running, stateful kind (see to_do_fbp.md): its processes must be
# Python classes deriving from FBPProcess or Supervisor.
DEBASHER_PROGRAM_TYPE_GENERAL="general"
DEBASHER_PROGRAM_TYPE_RESIDENT="resident"

# FIFO-RELATED CONSTANTS
DEBASHER_EXTERNAL_FIFO_USER="__EXTERNAL__${DEBASHER_ASSOC_ARRAY_ELEM_SEP}0"

# FLOW-BASED PROGRAMMING CONSTANTS
DEBASHER_SHUTDOWN_TOKEN="__SHUTDOWN_TOKEN__"

# FIFO MIRRORING CONSTANTS
#
# Deliberately distinct from DEBASHER_SHUTDOWN_TOKEN: not every fifo
# writer's own data-plane protocol emits a shutdown token (only
# "cycle"-style processes do), so a mirror tap's own termination can't
# depend on it.
DEBASHER_FIFO_MIRROR_STOP_TOKEN="__FIFO_MIRROR_TAP_STOP__"
# How long debasher::_stop_fifo_mirror_taps waits for a tap to stop on its
# token, and then again for it to end on SIGTERM, before going further.
DEBASHER_FIFO_MIRROR_TAP_STOP_GRACE_SECS=2

# RERUN REASONS
DEBASHER_PROC_STATUS_FIFO_RERUN_REASON="process_status_fifo_user_owner"
DEBASHER_FORCED_RERUN_REASON="forced"
DEBASHER_OUTDATED_CODE_RERUN_REASON="outdated_code"
DEBASHER_NEW_PROC_RERUN_REASON="new_process"
DEBASHER_INPUT_CHANGE_RERUN_REASON="input_change"
DEBASHER_PROPAGATE_FIFO_RERUN_REASON="propagate_fifo"
DEBASHER_PROPAGATE_DEPS_RERUN_REASON="propagate_dependencies"
DEBASHER_RESIDENT_RESUME_RERUN_REASON="resident_resume"

# PROCESS DEPENDENCIES
DEBASHER_NONE_PROCESSDEP_TYPE="none"
DEBASHER_AFTER_PROCESSDEP_TYPE="after"
DEBASHER_AFTEROK_PROCESSDEP_TYPE="afterok"
DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE="afternotok"
DEBASHER_AFTERANY_PROCESSDEP_TYPE="afterany"
DEBASHER_AFTERCORR_PROCESSDEP_TYPE="aftercorr"

# OPTION RELATED CONSTANTS
DEBASHER_OPT_FILE_LINES_PER_BLOCK=10000

# ASSOCIATIVE ARRAY TO STORE PRIORITY OF PROCESS DEPENDENCIES
declare -A DEBASHER_PROCESSDEP_PRIORITY
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_NONE_PROCESSDEP_TYPE}]=0
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_AFTERCORR_PROCESSDEP_TYPE}]=1
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_AFTER_PROCESSDEP_TYPE}]=2
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_AFTERANY_PROCESSDEP_TYPE}]=3
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_AFTEROK_PROCESSDEP_TYPE}]=4
DEBASHER_PROCESSDEP_PRIORITY[${DEBASHER_AFTERNOTOK_PROCESSDEP_TYPE}]=4

# PROCESS STATISTICS
DEBASHER_UNKNOWN_ELAPSED_TIME_FOR_PROCESS="UNKNOWN"

# PROGRAM STATUSES
#
# NOTE: exit code 1 is reserved for general errors when executing
# pipe_status
DEBASHER_PROGRAM_FINISHED_EXIT_CODE=0
DEBASHER_PROGRAM_IN_PROGRESS_EXIT_CODE=2
DEBASHER_PROGRAM_UNFINISHED_EXIT_CODE=3

# DEBASHER STATUS
DEBASHER_SCHEDULER=""
DEBASHER_BUILTIN_SCHEDULER="BUILTIN"
DEBASHER_SLURM_SCHEDULER="SLURM"

# SLURM-RELATED CONSTANTS
DEBASHER_FIRST_SLURM_VERSION_WITH_AFTERCORR="16.05"

# FILE EXTENSIONS
DEBASHER_STDOUT_FEXT="stdout"
DEBASHER_SCHED_LOG_FEXT="sched_out"
DEBASHER_OPTS_FEXT="opts"
DEBASHER_FINISHED_PROCESS_FEXT="finished"
DEBASHER_PROCESSID_FEXT="id"
DEBASHER_ARRAY_TASKID_FEXT="id"
DEBASHER_SLURM_EXEC_ATTEMPT_FEXT_STRING="__attempt"
DEBASHER_PROCSPEC_FEXT="procspec"
DEBASHER_PRGOPTS_FEXT="opts"
DEBASHER_PRGOPTS_OLD_FEXT="opts_old"
DEBASHER_PRGOPTS_EXHAUSTIVE_FEXT="opts_exh"
DEBASHER_FIFOS_FEXT="fifos"
DEBASHER_GRAPHS_FEXT="dot"
DEBASHER_SCHED_SCRIPT_INPUT_FEXT="opts"
DEBASHER_BASH_FEXT="sh"
DEBASHER_PYTHON_FEXT="py"
DEBASHER_PERL_FEXT="pl"
DEBASHER_R_FEXT="R"
DEBASHER_GROOVY_FEXT="groovy"

# File extensions for DEBASHER_HEREDOC_LANGUAGES/_INTERPRETERS, aligned
# with them by index (python/r/perl/groovy) -- lets an external file's
# language/interpreter (debasher::_get_doc_language_for_file/
# _get_interpreter_for_file in engine/debasher_lib_programs.sh) be
# looked up the same way, instead of its own separate case statement.
DEBASHER_HEREDOC_FEXTS=(
    "${DEBASHER_PYTHON_FEXT}"
    "${DEBASHER_R_FEXT}"
    "${DEBASHER_PERL_FEXT}"
    "${DEBASHER_GROOVY_FEXT}"
)

# FILE NAMES
DEBASHER_INITIAL_PROCSPEC_BASENAME=".initial_program.${DEBASHER_PROCSPEC_FEXT}"
DEBASHER_PRG_PREF="program"
DEBASHER_PRG_COMMAND_LINE_BASENAME="command_line.sh"
DEBASHER_DEBLIB_VARS_AND_FUNCS_BASENAME=".deblib_vars_and_funcs.sh"
DEBASHER_MOD_VARS_AND_FUNCS_BASENAME=".mod_vars_and_funcs.sh"
DEBASHER_TASK_MARKER_PREFIX="DEBASHER_TASK_DONE_"

# DIR_NAMES
DEBASHER_EXEC_DIRNAME="__exec__"
DEBASHER_GRAPHS_DIRNAME="__graphs__"
DEBASHER_FIFOS_DIRNAME="__fifos__"
DEBASHER_CONDA_DIRNAME=".conda"

# LOGGING CONSTANTS
DEBASHER_LOG_ERROR_MSG_START="Error:"
DEBASHER_LOG_WARNING_MSG_START="Warning:"
DEBASHER_RERUN_PROCESSES_WARNING="Warning: there are processes to rerun!"

# DEBASHER LIMITS
DEBASHER_MAX_NUM_PROCESSES=5000

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store help about program options
declare -A DEBASHER_PROGRAM_OPT_DESC
declare -A DEBASHER_PROGRAM_OPT_TYPE
declare -A DEBASHER_PROGRAM_OPT_IS_CMDLINE
declare -A DEBASHER_PROGRAM_OPT_IS_MANDATORY
declare -A DEBASHER_PROGRAM_OPT_CATEG
declare -A DEBASHER_PROGRAM_CATEG_MAP

# Declare array to store deserialized arguments
declare -a DEBASHER_DESERIALIZED_ARGS

# Declare associative array to memoize command line options
declare -A DEBASHER_MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
declare DEBASHER_LAST_PROC_LINE_MEMOPTS=""

# Declare string used to indicate current process during option
# definition
declare DEBASHER_DEFINE_OPTS_CURRENT_PROCESS=""

# Declare array to save option lists for current process (an array is
# needed to support multiple process executions)
declare -a DEBASHER_CURRENT_PROCESS_OPT_LIST

# Declare associative array used to save lengths of option lists for all
# processes
declare -A DEBASHER_PROCESS_OPT_LIST_LEN

# Declare associative array used to store initial process specification
declare -A DEBASHER_INITIAL_PROCESS_SPEC

# Declare associative array to store final process specification
declare -A DEBASHER_FINAL_PROCESS_SPEC

# Declare associative array used to map output values to processes
declare -A DEBASHER_OUT_VALUE_TO_PROCESSES

# Declare associative array used to store process dependencies
declare -A DEBASHER_PROCESS_DEPENDENCIES

# Declare associative array used to store simplified process
# dependencies (no task info is included)
declare -A DEBASHER_PROCESS_DEPENDENCIES_SIMPLIFIED

# Declare variable to store name of output directory
declare DEBASHER_PROGRAM_OUTDIR

# Declare array to store file names of loaded modules
declare -a DEBASHER_PROGRAM_MODULES

# Declare array to store, from the last module search, same-named
# candidates found one level below a DEBASHER_MOD_DIR entry that were
# rejected for not being a genuine DeBasher UI program directory (see
# debasher::_is_ui_program_dir in debasher_lib_modules.sh). Populated by
# debasher::_search_mod_in_dirs so that a subsequent "module not found"
# error can mention them.
declare -a DEBASHER_REJECTED_MOD_CANDIDATES

# Declare variable used by debasher::_search_mod_in_immediate_subdirs to
# hand its match back to debasher::_search_mod_in_dirs. A plain "echo
# and capture via $(...)" would run the function in a subshell, losing
# the DEBASHER_REJECTED_MOD_CANDIDATES entries it appends along the way
# -- so the match travels via this global instead.
declare DEBASHER_SUBDIR_MOD_MATCH

# Declare variable used by debasher::_search_mod_in_dirs and
# debasher::_determine_full_module_name to hand their resolved module
# path back to their callers (debasher::load_debasher_module and
# debasher::add_debasher_program) -- for the same reason as
# DEBASHER_SUBDIR_MOD_MATCH above: those callers need
# DEBASHER_REJECTED_MOD_CANDIDATES populated in their own shell, not a
# subshell's copy of it, so the whole chain is called directly instead
# of through $(...).
declare DEBASHER_RESOLVED_MODNAME

# Declare array to store a stack for the program files for each program
# function that is invoked
declare -a DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK

# Declare variable to store the current program's type (general or
# resident, see DEBASHER_PROGRAM_TYPE_* above); only the top-level
# pfile's `_program_type` method (if any) is ever resolved and
# invoked, so a composed sub-module's own `_program_type` has no
# effect
declare DEBASHER_PROGRAM_TYPE="${DEBASHER_PROGRAM_TYPE_GENERAL}"

# Declare associative array to store processes added to a program
declare -A DEBASHER_PROGRAM_PROCESSES

# Declare associative arrays to recover, for an alias/ext_alias process,
# what it actually delegates to -- the alias's target process name, or
# the ext_alias's resolved external file -- so debasher::_show_proc_implem
# (engine/debasher_lib_processes.sh) can document the real implementation
# instead of the synthesized wrapper function
# debasher::_create_process_func_alias/_ext_alias creates for it (see
# debasher::_add_debasher_alias_process/_add_debasher_ext_alias_process in
# engine/debasher_lib_programs.sh, which populate these).
declare -A DEBASHER_PROCESS_ALIAS_TARGETS
declare -A DEBASHER_PROCESS_EXT_ALIAS_FILES

# Declare associative array recording, for every process, the directory
# of the .sh that added it (dirname of
# DEBASHER_PROGRAM_FUNC_FOR_MODULE_PFILE_STACK's top at the time
# add_debasher_process ran) -- populated in
# debasher::add_debasher_process (engine/debasher_lib_programs.sh),
# since that stack only holds this while the program/module function
# adding the process is still running, but a process's own
# _define_opts function (where debasher::define_infile_opt needs it --
# see engine/debasher_lib_opts.sh) runs later, once that stack entry
# has already been popped.
declare -A DEBASHER_PROCESS_PFILE_DIR

# Declare array to store processes in topological order according to
# their dependencies
declare -a DEBASHER_PROGRAM_PROCESSES_TOPO_SORT

# Declare associative arrays to store name of shared directories
declare -A DEBASHER_PROGRAM_SHDIRS

# Declare associative arrays to store names of fifos
declare -A DEBASHER_PROGRAM_FIFOS

# Declare associative array to store users of fifos (The process
# defining the FIFO with debasher::define_fifo_opt becomes the owner)
declare -A DEBASHER_FIFO_USERS

# Declare associative array flagging which fifos (by augmented name,
# "<processname>/<fifoname>") were declared with define_fifo_opt's
# --mirror flag (see debasher::_start_fifo_mirror_taps_for_process)
declare -A DEBASHER_FIFO_MIRRORED

# Declare associative array with the tag of each tagged fifo (by augmented
# name), "control" or "external", given to define_fifo_opt or
# define_fifo_opt_generator as --control or --external: the reader's end of
# the fifo is a control port or an external port of a resident program's
# node, and a fifo fed from outside is owned by its reader (see the design
# doc's "Channel kinds declared with the fifo")
declare -A DEBASHER_FIFO_KINDS
DEBASHER_FIFO_KIND_CONTROL="control"
DEBASHER_FIFO_KIND_EXTERNAL="external"

# Declare associative array with the option through which the owner of each
# fifo (by augmented name) defines it: an output option ("-out...") if the
# owner writes it, an input option if it reads it
declare -A DEBASHER_FIFO_OWNER_OPTS

# Declare associative array with the option through which the process at the
# other end of each fifo (by augmented name) uses it, when that process is
# part of the program: an input option, since it reads the fifo
declare -A DEBASHER_FIFO_USER_OPTS

# Declare associative array with the role of each process of a resident
# program, "supervisor" or "fbpprocess" (see
# debasher::_validate_resident_program_processes)
declare -A DEBASHER_RESIDENT_PROCESS_ROLES

# Declare associative array with the ports of each task of the FBPProcess
# nodes and of the Supervisor of a resident program (by
# <process><DEBASHER_ASSOC_ARRAY_ELEM_SEP><idx>), which the wrapper of the
# task exports to it as DEBASHER_PROCESS_PORTS (see
# debasher::_register_resident_task_ports)
declare -A DEBASHER_RESIDENT_TASK_PORTS

# Declare general scheduler-related variables
declare DEBASHER_SCHEDULER
declare -A DEBASHER_RERUN_PROCESSES
declare -a DEBASHER_FORCED_RERUN_PROCESSES
declare DEBASHER_DEFAULT_NODES
declare DEBASHER_ARRAY_TASK_NOTHROTTLE=0
declare DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE=${DEBASHER_ARRAY_TASK_NOTHROTTLE}

# Declare SLURM scheduler-related variables
declare DEBASHER_AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM=0

# Declare associative array to store exit code for processes
declare -A DEBASHER_EXIT_CODE

######################
# INCLUDE BASH FILES #
######################

. "${debasher_pkglibdir}"/debasher_lib_utils
. "${debasher_pkglibdir}"/debasher_lib_programs
. "${debasher_pkglibdir}"/debasher_lib_modules
. "${debasher_pkglibdir}"/debasher_lib_process_spec
. "${debasher_pkglibdir}"/debasher_lib_processes
. "${debasher_pkglibdir}"/debasher_lib_opts
. "${debasher_pkglibdir}"/debasher_lib_mirror
. "${debasher_pkglibdir}"/debasher_lib_sched
. "${debasher_pkglibdir}"/debasher_lib_conda
. "${debasher_pkglibdir}"/debasher_lib_docker

#####################
# UTILITY FUNCTIONS #
#####################

debasher::list_public_functions()
{
    declare -F | "${AWK}" '{print $3}' | "${GREP}" -E "^${DEBASHER_DEBASHER_LIB_NAMESPACE}::[^_][A-Za-z0-9_]*$" | "${SORT}"
}
