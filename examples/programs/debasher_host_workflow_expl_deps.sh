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

# Load modules
load_debasher_module "debasher_host_workflow"

#################################
# PROGRAM DEFINED BY THE MODULE #
#################################

########
debasher_host_workflow_expl_deps_program()
{
    add_debasher_process "host1" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=none"
    add_debasher_process "host2" "cpus=1 mem=32 time=00:10:00 throttle=64" "processdeps=aftercorr:host1"
}
