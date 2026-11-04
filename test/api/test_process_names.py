import pytest

from api.process_names import process_name_problem


@pytest.mark.parametrize("name", ["hello", "org.mymodule.hello", "_x1"])
def test_a_name_the_engine_accepts_has_no_problem(name):
    assert process_name_problem(name) is None


# A name that ends with the suffix of a method of a process (the suffix
# carries its underscore), the termination handler of Slurm and the
# retired _outdir_basename included, or with that of a heredoc language,
# would make the process function of one process a method of another, and
# the engine refuses it, as it refuses the marker of its qualified names
@pytest.mark.parametrize(
    "name, reason",
    [
        ("1st", "letters, digits and underscores"),
        ("a-b", "letters, digits and underscores"),
        ("a..b", "letters, digits and underscores"),
        ("", "letters, digits and underscores"),
        ("a_define_opts", '"_define_opts"'),
        ("a_post", '"_post"'),
        ("a_document", '"_document"'),
        ("a_slurm_sigterm_handler", '"_slurm_sigterm_handler"'),
        ("a_outdir_basename", '"_outdir_basename"'),
        ("hello_py", '"_py"'),
        ("hello_heredoc_py", '"_py"'),
        ("a__NSSEP__b", '"__NSSEP__"'),
    ],
)
def test_a_name_the_engine_refuses_has_its_reason(name, reason):
    assert reason in process_name_problem(name)


def test_the_editor_checks_a_name_with_the_same_rule():
    # The router imports fastapi, which the system Python used by `make
    # check` may not have (the API's own requirements live in the
    # project's virtualenv, see api/README.md)
    pytest.importorskip("fastapi")
    from api.routers.processes import is_valid_process_name

    assert is_valid_process_name("org.mymodule.hello")
    assert not is_valid_process_name("a_post")
