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

from .debasher_constants import (
    PROCESS_METHOD_CONDA_ENVS_SUFFIX,
    PROCESS_METHOD_DOCKER_IMGS_SUFFIX,
    PROCESS_METHOD_OUTDIR_BASENAME_SUFFIX,
    PROCESS_METHOD_POST_SUFFIX,
    PROCESS_METHOD_RESET_OUTFILES_SUFFIX,
    PROCESS_METHOD_SKIP_SUFFIX,
)
from .markdown_parsing import function_body_lines
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


def resolve_additional_methods(methods_code: dict[str, str]) -> AdditionalMethods:
    fields: dict[str, str] = {}

    for suffix, field_name in _FIELD_BY_SUFFIX.items():
        source = methods_code.get(suffix.removeprefix("_"))
        if not source:
            continue
        body = function_body_lines(source)
        if body:
            fields[field_name] = "\n".join(body).strip()

    return AdditionalMethods(**fields)
