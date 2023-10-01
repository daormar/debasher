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

#############
# CONSTANTS #
#############

# STRING HANDLING
NOFILE="_NONE_"
ATTR_NOT_FOUND="_ATTR_NOT_FOUND_"
OPT_NOT_FOUND="_OPT_NOT_FOUND_"
DEP_NOT_FOUND="_DEP_NOT_FOUND_"
FUNCT_NOT_FOUND="_FUNCT_NOT_FOUND_"
VOID_VALUE="_VOID_VALUE_"
GENERAL_OPT_CATEGORY="GENERAL"
SPACE_SUBSTITUTE="__SPACE_SUBSTITUTE__"
ARG_SEP="<_ARG_SEP_>"
ARG_SEP_QUOTES="' '"
ARRAY_TASK_SEP=" ||| "
PROCESSNAME_SUFFIX_SEP="__"
PROCESSDEPS_SPEC="processdeps"
ATTEMPT_SEP=","
PROCESSDEPS_SEP_COMMA=","
PROCESSDEPS_SEP_INTERR="?"

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
DONT_EXECUTE_PROCESS_STATUS="DONT_EXECUTE"
DONT_EXECUTE_PROCESS_EXIT_CODE=6

# DONT_EXEC_REASONS
EXECFUNCT_DONT_EXEC_REASON="execfunct"

# REEXEC REASONS
FORCED_REEXEC_REASON="forced"
OUTDATED_CODE_REEXEC_REASON="outdated_code"
DEPS_REEXEC_REASON="dependencies"

# PROCESS DEPENDENCIES
AFTER_PROCESSDEP_TYPE="after"
AFTEROK_PROCESSDEP_TYPE="afterok"
AFTERNOTOK_PROCESSDEP_TYPE="afternotok"
AFTERANY_PROCESSDEP_TYPE="afterany"
AFTERCORR_PROCESSDEP_TYPE="aftercorr"

# PROCESS STATISTICS
UNKNOWN_ELAPSED_TIME_FOR_PROCESS="UNKNOWN"

# PIPELINE STATUSES
#
# NOTE: exit code 1 is reserved for general errors when executing
# pipe_status
PIPELINE_FINISHED_EXIT_CODE=0
PIPELINE_IN_PROGRESS_EXIT_CODE=2
PIPELINE_UNFINISHED_EXIT_CODE=3

# PANPIPE STATUS
PANPIPE_SCHEDULER=""
BUILTIN_SCHEDULER="BUILTIN"
SLURM_SCHEDULER="SLURM"

# SLURM-RELATED CONSTANTS
FIRST_SLURM_VERSION_WITH_AFTERCORR="16.05"

# FILE EXTENSIONS
BUILTIN_SCHED_LOG_FEXT="builtin_out"
SLURM_SCHED_LOG_FEXT="slurm_out"
FINISHED_PROCESS_FEXT="finished"
PROCESSID_FEXT="id"
ARRAY_TASKID_FEXT="id"
SLURM_EXEC_ATTEMPT_FEXT_STRING="__attempt"

# FILE NAMES
ORIGINAL_PIPELINE_BASENAME="original_pipeline.ppl"
REORDERED_PIPELINE_BASENAME="reordered_pipeline.ppl"
PPL_COMMAND_LINE_BASENAME="command_line.sh"

# DIR_NAMES
PANPIPE_SCRIPTS_DIRNAME="scripts"

# LOGGING CONSTANTS
PANPIPE_LOG_ERROR_MSG_START="Error:"
PANPIPE_LOG_WARNING_MSG_START="Warning:"
PANPIPE_REEXEC_PROCESSES_WARNING="Warning: there are processes to be re-executed!"

####################
# GLOBAL VARIABLES #
####################

# Declare associative arrays to store help about pipeline options
declare -A PIPELINE_OPT_DESC
declare -A PIPELINE_OPT_TYPE
declare -A PIPELINE_OPT_REQ
declare -A PIPELINE_OPT_CATEG
declare -A PIPELINE_CATEG_MAP
declare -A PIPELINE_OPT_PROCESS

# Declare array to store deserialized arguments
declare -a DESERIALIZED_ARGS

# Declare associative array to memoize command line options
declare -A MEMOIZED_OPTS

# Declare string variable to store last processed command line when
# memoizing options
declare LAST_PROC_LINE_MEMOPTS=""

# Declare array used to save option lists for scripts
declare -a SCRIPT_OPT_LIST_ARRAY

# Declare variable to store name of output directory
declare PIPELINE_OUTDIR

# Declare associative array to store names of loaded modules
declare -a PIPELINE_MODULES

# Declare associative array to store name of shared directories
declare -A PIPELINE_SHDIRS

# Declare associative array to store names of fifos
declare -A PIPELINE_FIFOS

# Declare general scheduler-related variables
declare PANPIPE_SCHEDULER
declare -A PANPIPE_REEXEC_PROCESSES
declare -A PANPIPE_REEXEC_PROCESSES_WITH_UPDATED_COMPLETION
declare -A PANPIPE_DONT_EXEC_PROCESSES
declare PANPIPE_DEFAULT_NODES
declare PANPIPE_DEFAULT_ARRAY_TASK_THROTTLE=1
declare PANPIPE_ARRAY_TASK_NOTHROTTLE=0

# Declare SLURM scheduler-related variables
declare AFTERCORR_PROCESSDEP_TYPE_AVAILABLE_IN_SLURM=0

# Declare associative array to store exit code for processes
declare -A EXIT_CODE

# INCLUDE BASH FILES
. "${panpipe_libexecdir}"/panpipe_lib_utils
. "${panpipe_libexecdir}"/panpipe_lib_pipelines
. "${panpipe_libexecdir}"/panpipe_lib_modules
. "${panpipe_libexecdir}"/panpipe_lib_processes
. "${panpipe_libexecdir}"/panpipe_lib_opts
. "${panpipe_libexecdir}"/panpipe_lib_sched
. "${panpipe_libexecdir}"/panpipe_lib_conda
