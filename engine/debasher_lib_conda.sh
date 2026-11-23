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

###########################
# CONDA-RELATED FUNCTIONS #
###########################

########
# Public: Creates a conda environment from a YAML file, unless an
# environment with that name exists already. A process calls it in its
# _conda_envs method, which a run with --conda-support executes before
# it launches anything.
#
# $1 - Name of the environment, or its absolute path.
# $2 - Name of the YAML file that describes the environment, searched in
#      the directories that DEBASHER_YML_DIR lists (separated by ":") and
#      then in the conda_envs directory of the DeBasher installation.
#
# Examples
#
#   debasher::define_conda_env py27 py27.yml
#
# The output of conda goes to <name>.log in the directory that
# DEBASHER_CONDA_DIR names, or else in the .conda directory of the output
# directory of the program; for an environment given by its absolute path,
# <name> is that path with every "/" turned into "_". Returns 0 if the environment exists or was
# created, 1 otherwise.
debasher::define_conda_env()
{
    local env_name=$1
    local yml_file=$2

    # Without conda there is nothing to look for nor to create with: the
    # error is given once, here
    debasher::_load_conda_functions || return 1

    if debasher::_conda_env_exists "${env_name}"; then
        return 0
    fi

    # Two runs that prepare the same environment at once (the batch runs
    # of a launcher node, two runs by hand) would both find it missing and
    # both create it, and the second would fail: a lock makes one create
    # it while the other waits and then finds it
    local lockdir=$(debasher::_get_conda_env_lock_dirname "${env_name}")
    debasher::_take_conda_env_lock "${lockdir}" || return 1
    local prepared=0
    if ! debasher::_conda_env_exists "${env_name}"; then
        local condadir=$(debasher::_get_absolute_condadir)

        # Obtain absolute yml file name
        local abs_yml_fname=$(debasher::_get_abs_yml_fname "${yml_file}")

        echo "Creating conda environment ${env_name} from file ${abs_yml_fname}..." >&2
        if debasher::_conda_env_prepare "${env_name}" "${abs_yml_fname}" "${condadir}"; then
            echo "Conda environment ${env_name} created" >&2
        else
            prepared=1
        fi
    fi
    "${RM}" -rf "${lockdir}"
    return ${prepared}
}

########
# Prints the directory that serves as the lock of the creation of the conda
# environment $1: under .conda of the home directory of the user, which
# conda itself keeps and which every run of the user shares, named after the
# environment (an absolute path with every "/" turned into "_"); without a
# home directory, under the temporary directory.
debasher::_get_conda_env_lock_dirname()
{
    local env_name=$1
    local base="${HOME:-${TMPDIR:-/tmp}}/.conda"
    echo "${base}/debasher_locks/${env_name//\//_}"
}

########
# Takes the lock $1 for this process: makes the directory, which is atomic,
# and leaves the id of this process in it. While another process holds it,
# waits, saying so once a minute; a lock whose holder is gone (its process
# id is not alive) is taken away and taken. Returns 1 if the directory
# cannot be made.
debasher::_take_conda_env_lock()
{
    local lockdir=$1
    "${MKDIR}" -p "$("${DIRNAME}" "${lockdir}")" || return 1
    local waited=0
    while ! "${MKDIR}" "${lockdir}" 2> /dev/null; do
        local holder=$("${CAT}" "${lockdir}/pid" 2> /dev/null)
        if [ -n "${holder}" ] && ! kill -0 "${holder}" 2> /dev/null; then
            echo "Taking away the lock of a conda environment left by process ${holder}, which is gone" >&2
            "${RM}" -rf "${lockdir}"
            continue
        fi
        if [ $((waited % 60)) -eq 0 ]; then
            echo "Waiting for process ${holder:-?} to finish creating the conda environment..." >&2
        fi
        "${SLEEP}" 2
        waited=$((waited + 2))
    done
    echo "$$" > "${lockdir}/pid"
}

########
# Public: Creates a conda environment from a YAML file, unless an
# environment with that name exists already. A process calls it in its
# _conda_envs method, which a run with --conda-support executes before
# it launches anything.
#
# $1 - Name of the environment, or its absolute path.
# $2 - Name of the YAML file that describes the environment, searched in
#      the directories that DEBASHER_YML_DIR lists (separated by ":") and
#      then in the conda_envs directory of the DeBasher installation.
#
# Examples
#
#   define_conda_env py27 py27.yml
#
# The output of conda goes to <name>.log in the directory that
# DEBASHER_CONDA_DIR names, or else in the .conda directory of the output
# directory of the program; for an environment given by its absolute path,
# <name> is that path with every "/" turned into "_". Returns 0 if the environment exists or was
# created, 1 otherwise.
define_conda_env() { debasher::define_conda_env "$@"; }

########
# Makes the shell functions of conda (conda activate, conda deactivate)
# available in the current shell, when they are not already: they are
# loaded from the conda executable, the one that the conda shell functions
# of the environment point to (CONDA_EXE) or else the one that configure
# found (CONDA_CMD), so that a process does not depend on how the shell that
# runs it was started. Returns 1, with an error, when there is no conda
# executable to load them from.
#
# The functions alone are not enough: they call the executable through
# CONDA_EXE, which their hook exports. A shell can have the functions and
# not the variable: a task gets the functions through the context of the
# process scripts, which leaves out exported variables, and inherits
# CONDA_EXE only when its environment comes from debasher_exec (not on a
# node of a Slurm job with --export=NONE, for instance). The hook is then
# loaded again, which defines CONDA_EXE.
debasher::_load_conda_functions()
{
    if declare -F conda > /dev/null && [ -f "${CONDA_EXE:-}" ] && [ -x "${CONDA_EXE:-}" ]; then
        return 0
    fi

    local conda_exe=${CONDA_EXE:-${CONDA_CMD}}
    if [ -z "${conda_exe}" ] || [ ! -f "${conda_exe}" ] || [ ! -x "${conda_exe}" ]; then
        echo "Error: conda was not found: there is no conda executable in CONDA_EXE, and configure found none (give it with ./configure CONDA_CMD=<conda executable>)" >&2
        return 1
    fi

    local hook
    hook=$("${conda_exe}" shell.bash hook) || {
        echo "Error: could not load the shell functions of conda from ${conda_exe}" >&2
        return 1
    }
    eval "${hook}"
}

########
# Public: Activates a conda environment in the current shell, loading the
# shell functions of conda first if the shell does not have them, so that
# it works however the shell that runs the process was started (a run, a
# Slurm job, debasher_exec_process, a business test). After it returns,
# `conda` itself (conda deactivate, another conda activate) can be used.
#
# $1 - Name of the environment, or its absolute path.
#
# Examples
#
#   conda_activate py27 || return 1
#
# Returns 0 if the environment was activated, 1 otherwise.
debasher::conda_activate()
{
    local env_name=$1

    debasher::_load_conda_functions || return 1
    conda activate "${env_name}"
}

########
# Public: Activates a conda environment in the current shell, loading the
# shell functions of conda first if the shell does not have them, so that
# it works however the shell that runs the process was started (a run, a
# Slurm job, debasher_exec_process, a business test). After it returns,
# `conda` itself (conda deactivate, another conda activate) can be used.
#
# $1 - Name of the environment, or its absolute path.
#
# Examples
#
#   conda_activate py27 || return 1
#
# Returns 0 if the environment was activated, 1 otherwise.
conda_activate() { debasher::conda_activate "$@"; }

########
# Creates the conda environments that the processes of the program declare
# in their _conda_envs methods, those that do not exist yet, as a run with
# --conda-support does before it launches anything and as debasher_test
# --conda-support does before the tests. Needs the program to be defined
# (DEBASHER_PROGRAM_PROCESSES). Returns 1 if an environment could not be
# created.
debasher::_prepare_conda_envs()
{
    echo "# Handling conda requirements (if any)..." >&2

    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local conda_envs_funcname=$(debasher::_get_conda_envs_funcname "${processname}")
        if debasher::_func_exists "${conda_envs_funcname}"; then
            echo "Handling conda requirements for process ${processname}..." >&2
            "${conda_envs_funcname}" || return 1
        fi
    done

    echo "Handling complete" >&2
    echo "" >&2
}

########
debasher::_conda_env_exists()
{
    local envname=$1
    local env_exists=1

    conda activate "${envname}" > /dev/null 2>&1 || env_exists=0

    if [ ${env_exists} -eq 1 ]; then
        conda deactivate
        return 0
    else
        return 1
    fi
}

########
debasher::_conda_env_prepare()
{
    local env_name=$1
    local abs_yml_fname=$2
    local condadir=$3
    local logf=$(debasher::_get_conda_env_log_fname "${condadir}" "${env_name}")

    # An absolute path is given to conda as the prefix of the environment,
    # a name as its name
    local env_flag="-n"
    if debasher::_is_absolute_path "${env_name}"; then
        env_flag="-p"
    fi

    conda env create -f "${abs_yml_fname}" "${env_flag}" "${env_name}" > "${logf}" 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${logf} file for more information" >&2; return 1; }
}

########
# Prints the log file of the creation of the conda environment env_name in
# the directory condadir: <name>.log, where the name of an environment given
# by its absolute path is that path with every "/" turned into "_", so that
# the log stays in condadir
debasher::_get_conda_env_log_fname()
{
    local condadir=$1
    local env_name=$2

    echo "${condadir}/${env_name//\//_}.log"
}

########
debasher::_get_debasher_yml_dir()
{
    echo "${debasher_datadir}/conda_envs"
}

########
debasher::_get_abs_yml_fname()
{
    local yml_fname=$1

    # Obtain array with directories
    debasher::_deserialize_args_given_sep "${DEBASHER_YML_DIR}" "${DEBASHER_YML_DIR_SEP}"

    # Search module in directories listed in DEBASHER_YML_DIR
    local dir
    local abs_yml_fname
    for dir in "${DEBASHER_DESERIALIZED_ARGS[@]}"; do
        if [ -f "${dir}/${yml_fname}" ]; then
            abs_yml_fname="${dir}/${yml_fname}"
            break
        fi
    done

    # Fallback to debasher yml package
    if [ -z "${abs_yml_fname}" ]; then
        debasher_yml_dir=$(debasher::_get_debasher_yml_dir)
        abs_yml_fname="${debasher_yml_dir}/${yml_fname}"
    fi

    echo "${abs_yml_fname}"
}
