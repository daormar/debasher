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

###########################
# CONDA-RELATED FUNCTIONS #
###########################

########
define_conda_env()
{
    local env_name=$1
    local yml_file=$2

    if ! conda_env_exists "${env_name}"; then
        local condadir=`get_absolute_condadir`

        # Obtain absolute yml file name
        local abs_yml_fname=`get_abs_yml_fname "${yml_file}"`

        echo "Creating conda environment ${env_name} from file ${abs_yml_fname}..." >&2
        conda_env_prepare "${env_name}" "${abs_yml_fname}" "${condadir}" || return 1
        echo "Package successfully installed"
    fi
}

########
conda_env_exists()
{
    local envname=$1
    local env_exists=1

    conda activate $envname > /dev/null 2>&1 || env_exists=0

    if [ ${env_exists} -eq 1 ]; then
        conda deactivate
        return 0
    else
        return 1
    fi
}

########
conda_env_prepare()
{
    local env_name=$1
    local abs_yml_fname=$2
    local condadir=$3

    if is_absolute_path "${env_name}"; then
        # Install packages given prefix name
        conda env create -f "${abs_yml_fname}" -p "${env_name}" > "${condadir}"/"${env_name}".log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/"${env_name}".log file for more information">&2 ; return 1; }
    else
        # Install packages given environment name
        conda env create -f "${abs_yml_fname}" -n "${env_name}" > "${condadir}"/"${env_name}".log 2>&1 || { echo "Error while preparing conda environment ${env_name} from ${abs_yml_fname} file. See ${condadir}/${env_name}.log file for more information">&2 ; return 1; }
    fi
}

########
get_debasher_yml_dir()
{
    echo "${debasher_datadir}/conda_envs"
}

########
get_abs_yml_fname()
{
    local yml_fname=$1

    # Obtain array with directories
    deserialize_args_given_sep "${DEBASHER_YML_DIR}" "${DEBASHER_YML_DIR_SEP}"

    # Search module in directories listed in DEBASHER_YML_DIR
    local dir
    local abs_yml_fname
    for dir in "${DESERIALIZED_ARGS[@]}"; do
        if [ -f "${dir}/${yml_fname}" ]; then
            abs_yml_fname="${dir}/${yml_fname}"
            break
        fi
    done

    # Fallback to debasher yml package
    if [ -z "${abs_yml_fname}" ]; then
        debasher_yml_dir=`get_debasher_yml_dir`
        abs_yml_fname="${debasher_yml_dir}/${yml_fname}"
    fi

    echo "${abs_yml_fname}"
}
