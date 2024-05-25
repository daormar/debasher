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

# Generate program definition API file
prog_def_symbols=("add_debasher_process()")
rm -f rtdocs/source/api_prog_def_doc.md
for name in "${prog_def_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_programs.sh >> rtdocs/source/api_prog_def_doc.md
done

# Generate module definition API file
mod_def_symbols=("load_debasher_module()")
rm -f rtdocs/source/api_mod_def_doc.md
for name in "${mod_def_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_programs.sh >> rtdocs/source/api_mod_def_doc.md
done
