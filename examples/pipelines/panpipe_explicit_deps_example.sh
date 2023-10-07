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

# Module imports
load_panpipe_module "panpipe_software_test"

########
panpipe_explicit_deps_example_pipeline()
{
    add_panpipe_process "process_a" "cpus=1 mem=32 time=00:01:00,00:02:00,00:03:00" "processdeps=none"
    add_panpipe_process "process_b" "cpus=1 mem=32 time=00:01:00" "processdeps=none"
    add_panpipe_process "process_c" "cpus=1 mem=32 time=00:01:00,00:02:00 throttle=2" "processdeps=none"
    add_panpipe_process "process_d" "cpus=1 mem=32 time=00:01:00" "processdeps=none"
    add_panpipe_process "process_e" "cpus=1 mem=32 time=00:01:00" "processdeps=after:process_d"
    add_panpipe_process "process_f" "cpus=1 mem=32 time=00:01:00" "processdeps=none"
    add_panpipe_process "process_g" "cpus=1 mem=32 time=00:01:00 throttle=4" "processdeps=aftercorr:process_c"
    add_panpipe_process "process_h" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:process_a?afterok:process_f"
    add_panpipe_process "process_i" "cpus=1 mem=32 time=00:01:00" "processdeps=afterok:process_b"
}
