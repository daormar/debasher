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

############################
# DOCKER-RELATED FUNCTIONS #
############################

########
# Pulls the docker images that the processes of the program declare in
# their _docker_imgs methods, those not present yet, as a run with
# --docker-support does before it launches anything and as debasher_test
# --docker-support does before the tests. Needs the program to be defined
# (DEBASHER_PROGRAM_PROCESSES). Returns 1 if an image could not be pulled.
debasher::_pull_docker_imgs()
{
    echo "# Handling docker requirements (if any)..." >&2

    local processname
    for processname in "${!DEBASHER_PROGRAM_PROCESSES[@]}"; do
        local docker_imgs_funcname=$(debasher::_get_docker_imgs_funcname "${processname}")
        if debasher::_func_exists "${docker_imgs_funcname}"; then
            echo "Handling docker requirements for process ${processname}..." >&2
            "${docker_imgs_funcname}" || return 1
        fi
    done

    echo "Handling complete" >&2
    echo "" >&2
}

########
debasher::pull_docker_img()
{
    local img_name=$1

    if ! debasher::_docker_img_exists "${img_name}"; then
        "${DOCKER}" pull "${img_name}" || return 1
    fi
}

pull_docker_img() { debasher::pull_docker_img "$@"; }

########
debasher::_docker_img_exists()
{
    local img_name=$1

    if "${DOCKER}" image inspect "${img_name}" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}
