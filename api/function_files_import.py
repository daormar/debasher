"""
Recovers from an imported module what script generation writes as calls
of the engine rather than as code of its own (see "Python function files"
in doc/design_doc_engine.md), so that a module generated from a program
imports back into the same program:

- the tasks of an array or an option generator, and the skip method, in a
  Python function file: a body that is exactly the call that script
  generation writes, with a path to a file beside the module, becomes the
  text of that file, in Python, with the path kept as the path of the file
  in the artifact;
- the Conda environments and the Docker images given as data: a
  conda_envs or docker_imgs body made only of define_conda_env or
  pull_docker_img calls with literal arguments becomes the list.

Anything else is left as the Bash it is, which runs the same: a body that
calls tasks_from_file with a file that is not there is still a Bash body
that calls it.
"""

import re
from pathlib import Path

from .models import CondaEnv, ProgramProcess

# A word between double quotes, or a bare one, with nothing that Bash would
# expand: the literal arguments that script generation writes
_WORD = r'(?:"(?P<{0}q>[^"$`\\]*)"|(?P<{0}b>[^\s"$`\\;|&]+))'

_PREFIX = r"(?:debasher::)?"

_TASKS_ARGS = r'"\$\{cmdline\}"\s+"\$\{process_name\}"\s+"\$\{process_outdir\}"'

_ARRAY_RE = re.compile(
    rf"^local array\n{_PREFIX}tasks_from_file\s+array\s+{_WORD.format('path')}\s+{_TASKS_ARGS}\s*\|\|\s*return 1$"
)
_COUNT_RE = re.compile(rf"^{_PREFIX}num_tasks_from_file\s+{_WORD.format('path')}\s+{_TASKS_ARGS}$")
_SKIP_RE = re.compile(rf'^{_PREFIX}skip_from_file\s+{_WORD.format("proc")}\s+{_WORD.format("path")}\s+"\$@"$')
_CONDA_RE = re.compile(
    rf"^{_PREFIX}define_conda_env\s+{_WORD.format('name')}\s+{_WORD.format('file')}(?:\s*\|\|\s*return 1)?$"
)
_DOCKER_RE = re.compile(rf"^{_PREFIX}pull_docker_img\s+{_WORD.format('img')}(?:\s*\|\|\s*return 1)?$")


def _word(match: re.Match, name: str) -> str:
    quoted = match.group(f"{name}q")
    return quoted if quoted is not None else match.group(f"{name}b")


def _statements(code: str | None) -> list[str]:
    """The lines of a body that say something, stripped, leaving out empty
    lines and comments."""
    return [line.strip() for line in (code or "").splitlines() if line.strip() and not line.strip().startswith("#")]


def _python_file_text(module_dir: Path, path: str) -> str | None:
    """The code in the Python file `path` of the module, without the
    newlines that end it, or None when the path is not that of a Python
    file beside the module that can be read."""
    if not path.endswith(".py"):
        return None
    try:
        return (module_dir / path).read_text().rstrip("\n")
    except OSError:
        return None


def _recover_tasks_file(process: ProgramProcess, module_dir: Path) -> None:
    handler = process.optionsHandler
    if handler.mode == "array":
        match = _ARRAY_RE.match("\n".join(_statements(handler.arrayCode)))
        field = "arrayCode"
    elif handler.mode == "generator":
        match = _COUNT_RE.match("\n".join(_statements(handler.generatorSizeCode)))
        field = "generatorSizeCode"
    else:
        return
    if match is None:
        return
    path = _word(match, "path")
    text = _python_file_text(module_dir, path)
    if text is None:
        return
    setattr(handler, field, text)
    handler.language = "python"
    process.files.tasks = path


def _recover_skip_file(process: ProgramProcess, module_dir: Path) -> None:
    methods = process.additionalMethods
    statements = _statements(methods.skipCode)
    match = _SKIP_RE.match(statements[0]) if len(statements) == 1 else None
    if match is None or _word(match, "proc") != process.name:
        return
    path = _word(match, "path")
    text = _python_file_text(module_dir, path)
    if text is None:
        return
    methods.skipCode = text
    methods.skipLanguage = "python"
    process.files.methods["skip"] = path


def _recover_env_data(process: ProgramProcess) -> None:
    methods = process.additionalMethods
    conda = [_CONDA_RE.match(line) for line in _statements(methods.condaEnvsCode)]
    if conda and all(conda):
        methods.condaEnvs = [CondaEnv(name=_word(m, "name"), file=_word(m, "file")) for m in conda]
        methods.condaEnvsCode = None
    docker = [_DOCKER_RE.match(line) for line in _statements(methods.dockerImgsCode)]
    if docker and all(docker):
        methods.dockerImgs = [_word(m, "img") for m in docker]
        methods.dockerImgsCode = None


def recover_function_files(process: ProgramProcess, module_dir: Path) -> None:
    """Gives `process`, imported from a module in `module_dir`, its tasks
    file and its skip file in Python and its Conda environments and Docker
    images as data, where the module holds them in the form that script
    generation writes."""
    _recover_tasks_file(process, module_dir)
    _recover_skip_file(process, module_dir)
    _recover_env_data(process)
