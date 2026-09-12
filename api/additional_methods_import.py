"""
Recovers a process's AdditionalMethods — reset_outfiles/post/
outdir_basename/skip/conda_envs/docker_imgs, the DEBASHER_PROCESS_METHODS
(engine/debasher_lib.sh) not already covered by ProcessInfo.description/
code/options/optionHandler — from the raw `declare -f` dumps
markdown_parsing.parse_methods_with_code pulls out of a process's
"### Process Methods" section, keyed by method label. Only populated
when debasher_doc_mod/debasher_get_proc_info were run with
--show-meths-with-code; a plain --show-meths (just bullet names, no
"#### <label>" subsections) yields nothing to recover here.

Each recovered field is the method's body alone (like arrayCode/
generatorSizeCode, unlike ProgramProcess.code) — script_generation.py's
_add_additional_methods_funcs re-wraps it into "<name><suffix>() { ... }"
on codegen, so only the body, not the function header/braces, is kept.
"""

from pathlib import Path

from .debasher_constants import (
    PROCESS_METHOD_CONDA_ENVS_SUFFIX,
    PROCESS_METHOD_DOCKER_IMGS_SUFFIX,
    PROCESS_METHOD_OUTDIR_BASENAME_SUFFIX,
    PROCESS_METHOD_POST_SUFFIX,
    PROCESS_METHOD_RESET_OUTFILES_SUFFIX,
    PROCESS_METHOD_SKIP_SUFFIX,
)
from .doc_mod import run_get_verbatim_func_source
from .markdown_parsing import (
    function_body_lines,
    function_header_name,
    join_verbatim_body_lines,
    verbatim_function_body_lines,
)
from .models import AdditionalMethods

# Method label (what debasher::_proc_method_label prints, i.e. the
# suffix with its leading separator stripped) -> AdditionalMethods field.
_FIELD_BY_SUFFIX = {
    PROCESS_METHOD_RESET_OUTFILES_SUFFIX: "resetOutfilesCode",
    PROCESS_METHOD_POST_SUFFIX: "postCode",
    PROCESS_METHOD_OUTDIR_BASENAME_SUFFIX: "outdirBasenameCode",
    PROCESS_METHOD_SKIP_SUFFIX: "skipCode",
    PROCESS_METHOD_CONDA_ENVS_SUFFIX: "condaEnvsCode",
    PROCESS_METHOD_DOCKER_IMGS_SUFFIX: "dockerImgsCode",
}


def resolve_additional_methods(
    methods_code: dict[str, str], script_path: Path, debasher_mod_dir: str = ""
) -> AdditionalMethods:
    fields: dict[str, str] = {}

    for suffix, field_name in _FIELD_BY_SUFFIX.items():
        source = methods_code.get(suffix.removeprefix("_"))
        if not source:
            continue
        body = function_body_lines(source)
        if not body:
            continue
        fields[field_name] = "\n".join(body).strip()

        # Best-effort upgrade to the method's exact original source
        # (comments/indentation intact) -- no fixed positional-arg
        # header to strip here (unlike arrayCode/generatorSizeCode),
        # since script_generation.py's _add_method_body_func wraps the
        # stored body straight into "<name><suffix>() { ... }" with no
        # header lines of its own — see this module's own docstring.
        funcname = function_header_name(source)
        if funcname is None:
            continue
        verbatim = run_get_verbatim_func_source(script_path, funcname, debasher_mod_dir)
        if not verbatim:
            continue
        verbatim_body = verbatim_function_body_lines(verbatim)
        if verbatim_body is not None:
            fields[field_name] = join_verbatim_body_lines(verbatim_body)

    return AdditionalMethods(**fields)
