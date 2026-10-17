"""
The option channels, the processes with several tasks (Array, Generator)
and the additional methods of a process, as the SDK puts them into the
program model, and what it refuses of them.
"""

from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from debasher import Array, DefinitionError, Generator, Process, Program  # noqa: E402


def _file(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def _work(tmp_path: Path) -> Process:
    return Process("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"))


def _model_options(process: Process, program: Program | None = None):
    program = program or Program("prg")
    program.add(process)
    return program.to_model().processes[-1].options


# --- channels ----------------------------------------------------------------


def test_a_fifo_output_is_a_fifo_channel_with_its_name(tmp_path):
    work = _work(tmp_path)
    work.fifo_output("-outf", "file", "the stream", "work_fifo", mirror=True)

    (option,) = _model_options(work)
    assert (option.direction, option.channel, option.value, option.mirror) == ("output", "fifo", "work_fifo", True)


def test_a_fifo_input_is_a_fifo_channel_external_if_said(tmp_path):
    work = _work(tmp_path)
    work.fifo_input("-inf", "string", "what comes in", "numbers", external=True)
    work.fifo_input("-other", "string", "what else comes in", "other")

    external, plain = _model_options(work)
    assert (external.direction, external.channel, external.value, external.fifoTag) == ("input", "fifo", "numbers", "external")
    assert plain.fifoTag is None


def test_an_outdir_option_names_the_process_output_directory_or_a_task_subdirectory(tmp_path):
    work = _work(tmp_path)
    work.outdir_opt("-outd", "the directory")
    work.outdir_opt("-outtask", "the task's", subpath="${task_idx}")

    whole, task = _model_options(work)
    assert (whole.direction, whole.dataType, whole.channel, whole.subpath) == ("output", "dir", "process_outdir", "")
    assert task.subpath == "${task_idx}"


def test_a_shared_dir_option_names_the_shared_directory(tmp_path):
    writer = _work(tmp_path)
    writer.shared_dir_opt("-outd", "dir", "where it writes", "shared", subpath="part_${task_idx}")
    reader = Process("reader", code=_file(tmp_path, "reader.sh", "reader()\n{\n    :\n}\n"))
    reader.shared_dir_opt("-ind", "dir", "where it reads", "shared", source=writer["-outd"])
    prg = Program("prg", shared_dirs=["shared"])
    prg.add(writer)
    prg.add(reader)

    model = prg.to_model()
    (writer_opt,), (reader_opt,) = (p.options for p in model.processes)
    assert (writer_opt.channel, writer_opt.value, writer_opt.subpath) == ("shared_dir", "shared", "part_${task_idx}")
    assert (reader_opt.direction, reader_opt.channel, reader_opt.value) == ("input", "shared_dir", "shared")
    assert len(model.edges) == 1


def test_a_procspec_option_takes_an_attribute_of_the_specifications(tmp_path):
    work = _work(tmp_path)
    work.procspec_opt("-cpus", "int", "the cpus", "cpus")

    (option,) = _model_options(work)
    assert (option.fromProcessSpec, option.value, option.commandLine) == (True, "cpus", False)


def test_a_value_desc_output_uses_the_value_desc_channel(tmp_path):
    work = _work(tmp_path)
    work.value_desc_output("-outv", "string", "a value")

    (option,) = _model_options(work)
    assert (option.direction, option.channel, option.value) == ("output", "value_desc", "")


@pytest.mark.parametrize("method", ["fifo_output", "outdir_opt", "value_desc_output"])
def test_an_output_method_wants_an_output_label(tmp_path, method):
    work = _work(tmp_path)
    args = {"fifo_output": ("-f", "file", "", "x"), "outdir_opt": ("-d", ""), "value_desc_output": ("-v", "string", "")}
    with pytest.raises(DefinitionError, match='starts with "-out"'):
        getattr(work, method)(*args[method])


def test_an_input_method_wants_an_input_label(tmp_path):
    work = _work(tmp_path)
    with pytest.raises(DefinitionError, match="is an output for the engine"):
        work.fifo_input("-outf", "file", "", "x")
    with pytest.raises(DefinitionError, match="is an output for the engine"):
        work.procspec_opt("-outf", "int", "", "cpus")


# --- fanout families -----------------------------------------------------------


def test_a_family_is_counted_by_an_option_of_the_same_process_given_as_object_or_label(tmp_path):
    work = _work(tmp_path)
    n = work.cmdline_opt("-n", "int", "how many")
    work.fifo_output("-outf-ith", "file", "the i'th", "fifo_${i}", count_source=n)
    work.output("-outd-ith", "dir", "the i'th dir", "${process_outdir}/${i}", count_source="-n")

    n_opt, by_object, by_label = _model_options(work)
    assert by_object.countSourceOptionId == n_opt.id
    assert by_label.countSourceOptionId == n_opt.id


def test_a_family_without_a_count_source_has_none_in_the_model(tmp_path):
    work = _work(tmp_path)
    work.output("-outf-ith", "file", "the i'th", "${process_outdir}/${i}")

    (option,) = _model_options(work)
    assert option.countSourceOptionId is None


def test_a_count_source_of_another_process_is_refused(tmp_path):
    other = Process("other", code=_file(tmp_path, "other.sh", "other()\n{\n    :\n}\n"))
    n = other.cmdline_opt("-n", "int", "")
    work = _work(tmp_path)
    work.output("-outf-ith", "file", "", "${process_outdir}/${i}", count_source=n)
    prg = Program("prg")
    prg.add(other)
    prg.add(work)

    with pytest.raises(DefinitionError, match="an option of the same process"):
        prg.to_model()


def test_a_count_source_the_process_does_not_declare_is_refused(tmp_path):
    work = _work(tmp_path)
    work.output("-outf-ith", "file", "", "${process_outdir}/${i}", count_source="-n")
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match='counted by "-n", which the process does not declare'):
        prg.to_model()


# --- arrays and generators -------------------------------------------------------


def test_an_array_carries_the_tasks_file_as_its_array_code(tmp_path):
    tasks = _file(tmp_path, "tasks.sh", 'local array=(a b c)\n')
    work = Array("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"), tasks=tasks)
    work.output("-outf", "file", "", "${process_outdir}/${array[$task_idx]}.txt")
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert process.optionsHandler.mode == "array"
    assert process.optionsHandler.arrayCode == "local array=(a b c)"
    assert process.optionsHandler.generatorSizeCode is None


def test_a_generator_carries_the_tasks_file_as_its_size_code(tmp_path):
    tasks = _file(tmp_path, "size.sh", "echo 3\n")
    work = Generator("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"), tasks=tasks)
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert process.optionsHandler.mode == "generator"
    assert process.optionsHandler.generatorSizeCode == "echo 3"
    assert process.optionsHandler.arrayCode is None


@pytest.mark.parametrize("cls, what", [(Array, "an array"), (Generator, "a generator")])
def test_a_tasked_process_needs_its_tasks_file(tmp_path, cls, what):
    with pytest.raises(DefinitionError, match=f"is {what} and gives no tasks= file"):
        cls("work", code="work.sh")


def test_a_missing_tasks_file_is_reported_when_the_program_is_written(tmp_path):
    work = Array("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"), tasks=tmp_path / "none.sh")
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="cannot read its tasks file"):
        prg.to_model()


def test_a_standard_process_takes_no_tasks_file(tmp_path):
    with pytest.raises(TypeError):
        Process("work", code="work.sh", tasks="tasks.sh")


def test_the_module_of_an_array_loops_over_its_array(tmp_path):
    tasks = _file(tmp_path, "tasks.sh", "local array=(a b c)")
    work = Array("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"), tasks=tasks)
    work.output("-outf", "file", "", "${process_outdir}/${array[$task_idx]}.txt")
    prg = Program("prg")
    prg.add(work)

    module = prg.write(tmp_path / "home").read_text()
    assert "    local array=(a b c)\n" in module
    assert 'for task_idx in "${!array[@]}"; do' in module


@pytest.mark.parametrize(
    "cls, field, code",
    [
        (Array, "arrayCode", "def tasks(run):\n    return ['a', 'b']"),
        (Generator, "generatorSizeCode", "def tasks(run):\n    return 2"),
    ],
)
def test_a_tasks_file_in_python_gives_a_handler_in_python(tmp_path, cls, field, code):
    work = cls("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
               tasks=_file(tmp_path, "work_tasks.py", code + "\n"))
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert process.optionsHandler.language == "python"
    assert getattr(process.optionsHandler, field) == code
    assert process.files.tasks == "work_tasks.py"


def test_a_tasks_file_of_another_extension_is_bash(tmp_path):
    work = Array("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                 tasks=_file(tmp_path, "tasks.txt", "local array=(a)\n"))
    prg = Program("prg")
    prg.add(work)

    assert prg.to_model().processes[0].optionsHandler.language == "bash"


def test_the_module_of_an_array_in_python_calls_its_tasks_file(tmp_path):
    work = Array("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                 tasks=_file(tmp_path, "work_tasks.py", "def tasks(run):\n    return ['a']\n"))
    prg = Program("prg")
    prg.add(work)

    home = tmp_path / "home"
    module = prg.write(home).read_text()
    assert ('    debasher::tasks_from_file array "work_tasks.py" "${cmdline}" "${process_name}" '
            '"${process_outdir}" || return 1\n') in module
    assert (home / "work_tasks.py").read_text() == "def tasks(run):\n    return ['a']\n"


# --- additional methods -----------------------------------------------------------


def test_the_additional_methods_come_from_their_files(tmp_path):
    work = Process(
        "work",
        code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
        skip=_file(tmp_path, "skip.sh", "return 1\n"),
        post=_file(tmp_path, "post.sh", "echo done\n"),
        reset_outfiles=_file(tmp_path, "reset.sh", 'rm -f "${outf}"\n'),
        outdir_basename=_file(tmp_path, "basename.sh", "echo work_out\n"),
        conda_envs=_file(tmp_path, "conda.sh", "define_conda_env py27 py27.yml\n"),
        docker_imgs=_file(tmp_path, "docker.sh", "define_docker_img ubuntu\n"),
    )
    prg = Program("prg")
    prg.add(work)

    methods = prg.to_model().processes[0].additionalMethods
    assert methods.skipCode == "return 1"
    assert methods.postCode == "echo done"
    assert methods.resetOutfilesCode == 'rm -f "${outf}"'
    assert methods.outdirBasenameCode == "echo work_out"
    assert methods.condaEnvsCode == "define_conda_env py27 py27.yml"
    assert methods.dockerImgsCode == "define_docker_img ubuntu"
    module = prg.write(tmp_path / "home").read_text()
    assert "work_conda_envs()\n{\n    define_conda_env py27 py27.yml\n}" in module


def test_a_skip_file_in_python_gives_a_skip_method_in_python(tmp_path):
    work = Process("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                   skip=_file(tmp_path, "work_skip.py", "def skip(task):\n    return False\n"))
    prg = Program("prg")
    prg.add(work)

    process = prg.to_model().processes[0]
    assert process.additionalMethods.skipLanguage == "python"
    assert process.additionalMethods.skipCode == "def skip(task):\n    return False"
    assert process.files.methods == {"skip": "work_skip.py"}
    module = prg.write(tmp_path / "home").read_text()
    assert 'work_skip()\n{\n    debasher::skip_from_file "work" "work_skip.py" "$@"\n}' in module


@pytest.mark.parametrize("method", ["post", "reset_outfiles", "outdir_basename", "conda_envs", "docker_imgs"])
def test_a_python_file_for_another_method_is_refused(tmp_path, method):
    with pytest.raises(DefinitionError, match="only the skip method takes one"):
        Process("work", code="work.sh", **{method: "method.py"})


def test_the_environments_given_as_data_go_into_the_model_and_the_module(tmp_path):
    work = Process("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                   conda_envs={"py27": "py27.yml", "tools": "tools.yml"},
                   docker_imgs=["ubuntu:24.04"])
    prg = Program("prg")
    prg.add(work)

    methods = prg.to_model().processes[0].additionalMethods
    assert [(env.name, env.file) for env in methods.condaEnvs] == [("py27", "py27.yml"), ("tools", "tools.yml")]
    assert methods.dockerImgs == ["ubuntu:24.04"]
    assert methods.condaEnvsCode is None and methods.dockerImgsCode is None
    module = prg.write(tmp_path / "home").read_text()
    assert ('work_conda_envs()\n{\n    debasher::define_conda_env "py27" "py27.yml" || return 1\n'
            '    debasher::define_conda_env "tools" "tools.yml" || return 1\n}') in module
    assert 'work_docker_imgs()\n{\n    debasher::pull_docker_img "ubuntu:24.04" || return 1\n}' in module


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"conda_envs": ["py27.yml"]}, "conda_envs is a dict"),
        ({"conda_envs": {"py27": ""}}, "conda_envs is a dict"),
        ({"docker_imgs": {"ubuntu": "24.04"}}, "docker_imgs is a list"),
        ({"docker_imgs": ["ubuntu", 3]}, "docker_imgs is a list"),
    ],
)
def test_environments_of_the_wrong_shape_are_refused(fields, message):
    with pytest.raises(DefinitionError, match=message):
        Process("work", code="work.sh", **fields)


def test_an_environment_that_the_module_cannot_write_is_refused_when_written(tmp_path):
    work = Process("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"),
                   docker_imgs=['ubuntu"; rm -rf /'])
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError):
        prg.write(tmp_path / "home")
    assert not (tmp_path / "home").exists()


def test_a_process_without_additional_methods_has_none(tmp_path):
    prg = Program("prg")
    prg.add(_work(tmp_path))

    methods = prg.to_model().processes[0].additionalMethods
    assert not methods.model_dump(exclude_defaults=True)


def test_a_missing_method_file_is_reported_when_the_program_is_written(tmp_path):
    work = Process("work", code=_file(tmp_path, "work.sh", "work()\n{\n    :\n}\n"), skip=tmp_path / "none.sh")
    prg = Program("prg")
    prg.add(work)

    with pytest.raises(DefinitionError, match="cannot read its method file"):
        prg.to_model()
