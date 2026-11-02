import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (the API's own requirements live in the
# project's virtualenv, see api/README.md). Skip this module in that case
# instead of failing the collection of the whole test directory.
pytest.importorskip("fastapi")

from api.routers.processes import is_valid_process_name  # noqa: E402


@pytest.mark.parametrize("name", ["hello", "org.mymodule.hello", "_x1"])
def test_a_name_the_engine_accepts_is_valid(name):
    assert is_valid_process_name(name)


# A name that ends with the suffix of a method of a process (the suffix
# carries its underscore), the termination handler of Slurm included, or
# with that of a heredoc language, would make the process function of one
# process a method of another, and the engine refuses it
@pytest.mark.parametrize(
    "name",
    ["1st", "a-b", "a_define_opts", "a_post", "a_document", "a_slurm_sigterm_handler", "hello_py", "hello_heredoc_py", "a__NSSEP__b"],
)
def test_a_name_the_engine_refuses_is_not_valid(name):
    assert not is_valid_process_name(name)
