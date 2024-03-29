#!/bin/bash

# Generate program command line options API file
cmdline_opts_symbols=("explain_cmdline_opt()")
rm -f rtdocs/source/api_cmdline_opts_doc.md
for name in "${cmdline_opts_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_cmdline_opts_doc.md
done

# Generate process options API file
proc_opts_symbols=("define_opt()")
rm -f rtdocs/source/api_proc_opts_doc.md
for name in "${proc_opts_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_opts_doc.md
done

# Generate process execution API file
proc_exec_symbols=("read_opt_value_from_func_args()")
rm -f rtdocs/source/api_proc_exec_doc.md
for name in "${proc_exec_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_exec_doc.md
done
