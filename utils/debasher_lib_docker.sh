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

############################
# DOCKER-RELATED FUNCTIONS #
############################

########
pull_docker_img()
{
    local img_name=$1

    if ! docker_img_exists "${img_name}"; then
        "${DOCKER}" pull "${img_name}" || return 1
    fi
}

########
docker_img_exists()
{
    local img_name=$1

    if "${DOCKER}" image inspect "${img_name}" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}
