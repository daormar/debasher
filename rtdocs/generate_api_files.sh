#!/bin/bash

# Generate process options API file
proc_opts_symbols=("define_opt()")
rm -f rtdocs/source/api_proc_opts_doc.md
for name in "${proc_opts_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_opts_doc.md
done

# Generate process implementation API file
proc_impl_symbols=("read_opt_value_from_func_args()")
rm -f rtdocs/source/api_proc_impl_doc.md
for name in "${proc_impl_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_proc_impl_doc.md
done

# Generate program command line options API file
cmdline_opts_symbols=("explain_cmdline_opt()")
rm -f rtdocs/source/api_cmdline_opts_doc.md
for name in "${cmdline_opts_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_opts.sh >> rtdocs/source/api_cmdline_opts_doc.md
done

# Generate module configuration API file
mod_conf_symbols=("load_debasher_module()")
rm -f rtdocs/source/api_mod_conf_doc.md
for name in "${mod_conf_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_programs.sh >> rtdocs/source/api_mod_conf_doc.md
done

# Generate program definition API file
prog_def_symbols=("add_debasher_process()")
rm -f rtdocs/source/api_prog_def_doc.md
for name in "${prog_def_symbols[@]}"; do
    sh rtdocs/tomdoc.sh -m -s "${name}" utils/debasher_lib_programs.sh >> rtdocs/source/api_prog_def_doc.md
done
