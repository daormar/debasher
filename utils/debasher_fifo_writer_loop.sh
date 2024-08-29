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

# Check if the correct number of arguments is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <string> <fifo_name>"
    exit 1
fi

# Assign arguments to variables
STRING=$1
FIFO=$2
TIMEOUT=1

# Check if the FIFO exists; if not, create it
if [ ! -p "$FIFO" ]; then
    mkfifo "$FIFO"
fi

# Infinite loop to write the string to the FIFO

# NOTE: The timeout is necessary to prevent issues on the reader's end.
# If the reader stops in the middle of a write operation, this script may
# receive a SIGPIPE signal. The sleep command helps ensure that no additional
# writes occur during a read operation.
while true; do
    echo "$STRING" > "$FIFO"
    sleep "${TIMEOUT}"
done
