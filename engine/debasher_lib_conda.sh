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
debasher::define_conda_env()
{
    local env_name=$1
    local yml_file=$2

    if ! debasher::_conda_env_exists "${env_name}"; then
        local condadir=$(debasher::_get_absolute_condadir)

        # Obtain absolute yml file name
        local abs_yml_fname=$(debasher::_get_abs_yml_fname "${yml_file}")

        echo "Creating conda environment ${env_name} from file ${abs_yml_fname}..." >&2
        debasher::_conda_env_prepare "${env_name}" "${abs_yml_fname}" "${condadir}" || return 1
        echo "Package successfully installed"
    fi
}

define_conda_env() { debasher::define_conda_env "$@"; }

########
# Makes the shell functions of conda (conda activate, conda deactivate)
# available in the current shell, when they are not already: they are
# loaded from the conda executable, the one that the conda shell functions
# of the environment point to (CONDA_EXE) or else the one that configure
# found (CONDA), so that a process does not depend on how the shell that
# runs it was started. Returns 1, with an error, when there is no conda
# executable to load them from.
debasher::_load_conda_functions()
{
    if declare -F conda > /dev/null; then
        return 0
    fi

    local conda_exe=${CONDA_EXE:-${CONDA}}
    if [ -z "${conda_exe}" ] || [ ! -x "${conda_exe}" ]; then
        echo "Error: conda was not found: there is no conda executable in CONDA_EXE, and configure found none (give it with ./configure CONDA=<conda executable>)" >&2
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

    debasher::_load_conda_functions || return 1

    conda activate $envname > /dev/null 2>&1 || env_exists=0

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

    debasher::_load_conda_functions || return 1

    if debasher::_is_absolute_path "${env_name}"; then
        # Install packages given prefix name
        conda env create -f "${abs_yml_fname}" -p "${env_name}" > "${condadir}"/"${env_name}".log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/"${env_name}".log file for more information">&2 ; return 1; }
    else
        # Install packages given environment name
        conda env create -f "${abs_yml_fname}" -n "${env_name}" > "${condadir}"/"${env_name}".log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/${env_name}.log file for more information">&2 ; return 1; }
    fi
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
