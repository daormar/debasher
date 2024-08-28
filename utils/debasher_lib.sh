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

# *- bash -*

#############
# CONSTANTS #
#############

# STRING HANDLING
NOFILE="_NONE_"
ATTR_NOT_FOUND="_ATTR_NOT_FOUND_"
OPT_NOT_FOUND="_OPT_NOT_FOUND_"
DEP_NOT_FOUND="_DEP_NOT_FOUND_"
FUNCT_NOT_FOUND="_FUNCT_NOT_FOUND_"
VAR_NOT_FOUND="_VAR_NOT_FOUND_"
VOID_VALUE="_VOID_VALUE_"
GENERAL_OPT_CATEGORY="GENERAL"
SPACE_SUBSTITUTE="__SPACE_SUBSTITUTE__"
ARG_SEP="<_ARG_SEP_>"
ARG_SEP_QUOTES="' '"
ARRAY_TASK_SEP=" ||| "
PROCESSNAME_SUFFIX_SEP="__"
PROCESSDEPS_SPEC="processdeps"
ATTEMPT_SEP=","
PROCESS_PLUS_DEPTYPE_SEP=":"
PROCESSDEPS_SEP_COMMA=","
PROCESSDEPS_SEP_INTERR="?"
ASSOC_ARRAY_ELEM_SEP="__ELEMSEP__"
ASSOC_ARRAY_KEY_LEN="__LEN__"
ASSOC_ARRAY_PROC_SEP="__PROCSEP__"
DEBASHER_MOD_DIR_SEP=":"
DEBASHER_YML_DIR_SEP=":"
PROCESS_METHOD_SEP="_"
MODULE_METHOD_SEP="_"
VALUE_DESCRIPTOR_NAME_PREFIX=".__VAL_DESCRIPTOR__"
PROC_OUT_OPT_DESCRIPTOR_NAME_PREFIX="__PROC_OUT_OPT_DESCRIPTOR__"
SCHED_OPTS_DIRNAME=".sched_opts"
SCHED_OPTS_FNAME_FOR_PROCESS_PREFIX="sched_opts_"
SHDIR_MODULE_OWNER="__SHDIR_MODULE_OWNER__"
OPTLIST_VARNAME_SUFFIX="optlist"
END_OF_OPTIONS_MARKER="--"

# INVALID IDENTIFIERS
INVALID_SID="_INVALID_SID_"
INVALID_JID="_INVALID_JID_"
INVALID_PID="_INVALID_PID_"
INVALID_ARRAY_TID="_INVALID_ARRAY_TID_"

# PROCESS STATUSES AND EXIT CODES
FINISHED_PROCESS_STATUS="FINISHED"
FINISHED_PROCESS_EXIT_CODE=0
INPROGRESS_PROCESS_STATUS="IN-PROGRESS"
INPROGRESS_PROCESS_EXIT_CODE=1
UNFINISHED_BUT_RUNNABLE_PROCESS_STATUS="UNFINISHED_BUT_RUNNABLE"
UNFINISHED_BUT_RUNNABLE_PROCESS_EXIT_CODE=2
UNFINISHED_PROCESS_STATUS="UNFINISHED"
UNFINISHED_PROCESS_EXIT_CODE=3
REEXEC_PROCESS_STATUS="REEXECUTE"
REEXEC_PROCESS_EXIT_CODE=4
TODO_PROCESS_STATUS="TO-DO"
TODO_PROCESS_EXIT_CODE=5

# PROCESS METHOD NAMES
PROCESS_METHOD_NAME_DOCUMENT="${PROCESS_METHOD_SEP}document"
PROCESS_METHOD_NAME_RESET_OUTFILES="${PROCESS_METHOD_SEP}reset_outfiles"
PROCESS_METHOD_NAME_EXEC=""
PROCESS_METHOD_NAME_PYEXEC="${PROCESS_METHOD_SEP}py"
PROCESS_METHOD_NAME_REXEC="${PROCESS_METHOD_SEP}r"
PROCESS_METHOD_NAME_PERLEXEC="${PROCESS_METHOD_SEP}perl"
PROCESS_METHOD_NAME_GROOVYEXEC="${PROCESS_METHOD_SEP}groovy"
PROCESS_METHOD_NAME_POST="${PROCESS_METHOD_SEP}post"
PROCESS_METHOD_NAME_OUTDIR="${PROCESS_METHOD_SEP}outdir_basename"
PROCESS_METHOD_NAME_EXPLAIN_CMDLINE_OPTS="${PROCESS_METHOD_SEP}explain_cmdline_opts"
PROCESS_METHOD_NAME_DEFINE_OPTS="${PROCESS_METHOD_SEP}define_opts"
PROCESS_METHOD_NAME_DEFINE_OPT_DEPS="${PROCESS_METHOD_SEP}define_opt_deps"
PROCESS_METHOD_NAME_GENERATE_OPTS_SIZE="${PROCESS_METHOD_SEP}generate_opts_size"
PROCESS_METHOD_NAME_GENERATE_OPTS="${PROCESS_METHOD_SEP}generate_opts"
PROCESS_METHOD_NAME_SKIP="${PROCESS_METHOD_SEP}skip"
PROCESS_METHOD_NAME_CONDA_ENVS="${PROCESS_METHOD_SEP}conda_envs"
PROCESS_METHOD_NAME_DOCKER_IMGS="${PROCESS_METHOD_SEP}docker_imgs"

# MODULE METHOD NAMES
MODULE_METHOD_NAME_DOCUMENT="${MODULE_METHOD_SEP}document"
MODULE_METHOD_NAME_SHRDIRS="${MODULE_METHOD_SEP}shared_dirs"
MODULE_METHOD_NAME_PROGRAM="${MODULE_METHOD_SEP}program"

# FIFO-RELATED CONSTANTS
EXTERNAL_FIFO_USER="__EXTERNAL__${ASSOC_ARRAY_ELEM_SEP}0"

# FLOW-BASED PROGRAMMING CONSTANTS
SHUTDOWN_TOKEN="__SHUTDOWN_TOKEN__"

# REEXEC REASONS
FIFO_REEXEC_REASON="fifo"
FORCED_REEXEC_REASON="forced"
OUTDATED_CODE_REEXEC_REASON="outdated_code"
DEPS_REEXEC_REASON="dependencies"

# PROCESS DEPENDENCIES
NONE_PROCESSDEP_TYPE="none"
AFTER_PROCESSDEP_TYPE="after"
AFTEROK_PROCESSDEP_TYPE="afterok"
AFTERNOTOK_PROCESSDEP_TYPE="afternotok"
AFTERANY_PROCESSDEP_TYPE="afterany"
AFTERCORR_PROCESSDEP_TYPE="aftercorr"

# OPTION RELATED CONSTANTS
OPT_FILE_LINES_PER_BLOCK=10000

# ASSOCIATIVE ARRAY TO STORE PRIORITY OF PROCESS DEPENDENCIES
declare -A PROCESSDEP_PRIORITY
PROCESSDEP_PRIORITY[${NONE_PROCESSDEP_TYPE}]=0
PROCESSDEP_PRIORITY[${AFTERCORR_PROCESSDEP_TYPE}]=1
PROCESSDEP_PRIORITY[${AFTER_PROCESSDEP_TYPE}]=2
PROCESSDEP_PRIORITY[${AFTERANY_PROCESSDEP_TYPE}]=3
PROCESSDEP_PRIORITY[${AFTEROK_PROCESSDEP_TYPE}]=4
PROCESSDEP_PRIORITY[${AFTERNOTOK_PROCESSDEP_TYPE}]=4

# PROCESS STATISTICS
UNKNOWN_ELAPSED_TIME_FOR_PROCESS="UNKNOWN"

# PROGRAM STATUSES
#
# NOTE: exit code 1 is reserved for general errors when executing
# pipe_status
PROGRAM_FINISHED_EXIT_CODE=0
PROGRAM_IN_PROGRESS_EXIT_CODE=2
PROGRAM_UNFINISHED_EXIT_CODE=3

# DEBASHER STATUS
DEBASHER_SCHEDULER=""
BUILTIN_SCHEDULER="BUILTIN"
SLURM_SCHEDULER="SLURM"

# SLURM-RELATED CONSTANTS
FIRST_SLURM_VERSION_WITH_AFTERCORR="16.05"

# FILE EXTENSIONS
STDOUT_FEXT="stdout"
SCHED_LOG_FEXT="sched_out"
FINISHED_PROCESS_FEXT="finished"
PROCESSID_FEXT="id"
ARRAY_TASKID_FEXT="id"
SLURM_EXEC_ATTEMPT_FEXT_STRING="__attempt"
PROCSPEC_FEXT="procspec"
PRGOPTS_FEXT="opts"
PRGOPTS_EXHAUSTIVE_FEXT="opts_exh"
FIFOS_FEXT="fifos"
GRAPHS_FEXT="dot"
SCHED_SCRIPT_INPUT_FEXT="opts"

# FILE NAMES
PPEXEC_INITIAL_PROCSPEC_BASENAME=".initial_program.${PROCSPEC_FEXT}"
PPEXEC_PRG_PREF="program"
PRG_COMMAND_LINE_BASENAME="command_line.sh"
DEBLIB_VARS_AND_FUNCS_BASENAME=".deblib_vars_and_funcs.sh"
MOD_VARS_AND_FUNCS_BASENAME=".mod_vars_and_funcs.sh"

# DIR_NAMES
DEBASHER_EXEC_DIRNAME="__exec__"
DEBASHER_GRAPHS_DIRNAME="__graphs__"
DEBASHER_FIFOS_DIRNAME="__fifos__"
DEBASHER_CONDA_DIRNAME=".conda"

# LOGGING CONSTANTS
DEBASHER_LOG_ERROR_MSG_START="Error:"
DEBASHER_LOG_WARNING_MSG_START="Warning:"
DEBASHER_REEXEC_PROCESSES_WARNING="Warning: there are processes to be re-executed!"

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store help about program options
declare -A PROGRAM_OPT_DESC
declare -A PROGRAM_OPT_TYPE
declare -A PROGRAM_OPT_REQ
declare -A PROGRAM_OPT_CATEG
declare -A PROGRAM_CATEG_MAP
declare -A PROGRAM_OPT_PROCESS

# Declare array to store deserialized arguments
declare -a DESERIALIZED_ARGS

# Declare associative array to memoize command line options
declare -A MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
declare LAST_PROC_LINE_MEMOPTS=""

# Declare string used to indicate current process during option
# definition
declare DEFINE_OPTS_CURRENT_PROCESS=""

# Declare array to save option lists for current process (an array is
# needed to support multiple process executions)
declare -a CURRENT_PROCESS_OPT_LIST

# Declare associative array used to save lengths of option lists for all
# processes
declare -A PROCESS_OPT_LIST_LEN

# Declare associative array used to store initial process specification
declare -A INITIAL_PROCESS_SPEC

# Declare associative array used to map output values to processes
declare -A OUT_VALUE_TO_PROCESSES

# Declare associative array used to store process dependencies
declare -A PROCESS_DEPENDENCIES

# Declare variable storing whether all process dependencies where
# pre-specified in initial process specification
declare ALL_PROCESS_DEPS_PRE_SPECIFIED

# Declare variable to store name of output directory
declare PROGRAM_OUTDIR

# Declare array to store file names of loaded modules
declare -a PROGRAM_MODULES

# Declare associative array to store processes added to a program
declare -A PROGRAM_PROCESSES

# Declare associative arrays to store name of shared directories
declare -A PROGRAM_SHDIRS

# Declare associative arrays to store names of fifos
declare -A PROGRAM_FIFOS

# Declare associative array to store users of fifos (The process
# defining the FIFO with define_fifo_opt becomes the owner)
declare -A FIFO_USERS

# Declare general scheduler-related variables
declare DEBASHER_SCHEDULER
declare -A DEBASHER_REEXEC_PROCESSES
declare -A DEBASHER_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION
declare DEBASHER_DEFAULT_NODES
declare DEBASHER_DEFAULT_ARRAY_TASK_THROTTLE=1
declare DEBASHER_ARRAY_TASK_NOTHROTTLE=0

# Declare SLURM scheduler-related variables
declare AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM=0

# Declare associative array to store exit code for processes
declare -A EXIT_CODE

# INCLUDE BASH FILES
. "${debasher_libexecdir}"/debasher_lib_utils
. "${debasher_libexecdir}"/debasher_lib_programs
. "${debasher_libexecdir}"/debasher_lib_modules
. "${debasher_libexecdir}"/debasher_lib_processes
. "${debasher_libexecdir}"/debasher_lib_opts
. "${debasher_libexecdir}"/debasher_lib_sched
. "${debasher_libexecdir}"/debasher_lib_conda
. "${debasher_libexecdir}"/debasher_lib_docker
