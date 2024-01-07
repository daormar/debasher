#!/bin/bash

# Generate process options API file
proc_opts_symbols=("define_opt()")
rm -f rtdocs/source/api_proc_opts_doc.md
for name in "${proc_opts_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_opts_doc.md
done
