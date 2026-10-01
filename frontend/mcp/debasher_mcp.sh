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

# *- bash -*

# debasher_mcp runs the MCP server of DeBasher, the JavaScript module that
# the build of the frontend bundles, under Node.js. Its options (--url,
# --help) are those of the server itself, to which they are passed as they
# are.

########
resolve_node()
{
    # Prefer an explicit override, then the node found at configure time,
    # then whatever "node" resolves to on PATH (a source tree that came with
    # a prebuilt frontend is configured without looking for one).
    if [ -n "${DEBASHER_MCP_NODE:-}" ]; then
        NODE="${DEBASHER_MCP_NODE}"
    elif [ -n "${debasher_node}" ] && [ -x "${debasher_node}" ]; then
        NODE="${debasher_node}"
    elif command -v node >/dev/null 2>&1; then
        NODE="node"
    else
        echo "Error: debasher_mcp needs Node.js, and none was found" >&2
        echo "Put node in the PATH, or point DEBASHER_MCP_NODE at it" >&2
        exit 1
    fi
}

########

resolve_node

exec "${NODE}" "${debasher_pkgdatadir}/mcp/debasher_mcp.mjs" "$@"
