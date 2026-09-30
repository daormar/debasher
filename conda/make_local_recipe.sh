#!/bin/bash
# Usage: make_local_recipe.sh <tarball> <outdir>
#
# Writes into <outdir> a copy of this recipe whose source is the local
# release tarball <tarball> (one built with "make dist-vendored"), with
# its sha256, instead of the asset of a published release: the recipe
# can then be built before that release exists.

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <tarball> <outdir>" >&2
    exit 1
fi

tarball=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
outdir=$2
recipedir=$(cd "$(dirname "$0")" && pwd)

mkdir -p "${outdir}"
cp "${recipedir}/meta.yaml" "${recipedir}/build.sh" "${recipedir}/run_test.sh" \
   "${recipedir}/conda_build_config.yaml" "${outdir}/"

# Python rather than sed -i and sha256sum, which differ between Linux and
# macOS
python3 - "${tarball}" "${outdir}/meta.yaml" <<'EOF'
import hashlib, re, sys
tarball, meta = sys.argv[1], sys.argv[2]
with open(tarball, "rb") as f:
    sha = hashlib.sha256(f.read()).hexdigest()
with open(meta) as f:
    text = f.read()
text, nurl = re.subn(r"(?m)^  url: .*$", f"  url: file://{tarball}", text)
text, nsha = re.subn(r"(?m)^  sha256: .*$", f"  sha256: {sha}", text)
if nurl != 1 or nsha != 1:
    sys.exit(f"{meta}: expected one source url and one sha256")
with open(meta, "w") as f:
    f.write(text)
EOF
