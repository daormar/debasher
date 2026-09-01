# Mirrors naming-related constants from engine/debasher_lib.sh. Kept
# here as the single source of truth for engine-reserved suffixes, so
# both process-name validation and script generation stay in sync with
# the engine's own conventions instead of duplicating them.

# Mirrors the individual DEBASHER_PROCESS_METHOD_NAME_* constants.
PROCESS_METHOD_DOCUMENT_SUFFIX = "_document"
PROCESS_METHOD_RESET_OUTFILES_SUFFIX = "_reset_outfiles"
PROCESS_METHOD_EXEC_SUFFIX = ""
PROCESS_METHOD_POST_SUFFIX = "_post"
PROCESS_METHOD_OUTDIR_BASENAME_SUFFIX = "_outdir_basename"
PROCESS_METHOD_EXPLAIN_CMDLINE_OPTS_SUFFIX = "_explain_cmdline_opts"
PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX = "_explain_opts"
PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX = "_identify_cmdline_opts"
PROCESS_METHOD_DEFINE_OPTS_SUFFIX = "_define_opts"
PROCESS_METHOD_DEFINE_OPT_DEPS_SUFFIX = "_define_opt_deps"
PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX = "_generate_opts_size"
PROCESS_METHOD_GENERATE_OPTS_SUFFIX = "_generate_opts"
PROCESS_METHOD_SKIP_SUFFIX = "_skip"
PROCESS_METHOD_CONDA_ENVS_SUFFIX = "_conda_envs"
PROCESS_METHOD_DOCKER_IMGS_SUFFIX = "_docker_imgs"

# Mirrors DEBASHER_PROCESS_METHODS: suffixes DeBasher appends to a
# process name to build its method function names (e.g.
# "<name>_document", "<name>_post"). PROCESS_METHOD_EXEC_SUFFIX ("") is
# the exec method's own (empty) suffix, kept to preserve the engine's
# exact behavior, which also rejects any name ending in a bare "_".
RESERVED_PROCESS_METHOD_SUFFIXES = [
    PROCESS_METHOD_DOCUMENT_SUFFIX,
    PROCESS_METHOD_RESET_OUTFILES_SUFFIX,
    PROCESS_METHOD_EXEC_SUFFIX,
    PROCESS_METHOD_POST_SUFFIX,
    PROCESS_METHOD_OUTDIR_BASENAME_SUFFIX,
    PROCESS_METHOD_EXPLAIN_CMDLINE_OPTS_SUFFIX,
    PROCESS_METHOD_EXPLAIN_OPTS_SUFFIX,
    PROCESS_METHOD_IDENTIFY_CMDLINE_OPTS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPTS_SUFFIX,
    PROCESS_METHOD_DEFINE_OPT_DEPS_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SIZE_SUFFIX,
    PROCESS_METHOD_GENERATE_OPTS_SUFFIX,
    PROCESS_METHOD_SKIP_SUFFIX,
    PROCESS_METHOD_CONDA_ENVS_SUFFIX,
    PROCESS_METHOD_DOCKER_IMGS_SUFFIX,
]

# Mirrors DEBASHER_HEREDOC_SUFFIXES: language suffixes reserved for
# heredoc process variables (e.g. "<name>_py").
RESERVED_HEREDOC_SUFFIXES = ["py", "r", "perl", "groovy"]

# Mirrors the individual DEBASHER_MODULE_METHOD_NAME_* constants.
MODULE_DOCUMENT_SUFFIX = "_document"
MODULE_SHARED_DIRS_SUFFIX = "_shared_dirs"
MODULE_PROGRAM_SUFFIX = "_program"

# Mirrors DEBASHER_MODULE_METHODS: suffixes DeBasher appends to a
# module (program) name to build its module-level function names.
RESERVED_MODULE_METHOD_SUFFIXES = [
    MODULE_DOCUMENT_SUFFIX,
    MODULE_SHARED_DIRS_SUFFIX,
    MODULE_PROGRAM_SUFFIX,
]
