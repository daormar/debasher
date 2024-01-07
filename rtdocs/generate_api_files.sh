#!/bin/bash

# Generate process options API file
rm -f rtdocs/source/api_proc_opts_doc.md
for name in "define_opt()"; do
    sh rtdocs/tomdoc.sh -m -a Public -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_opts_doc.md
done
