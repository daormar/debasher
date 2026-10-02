import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (the API's own requirements live in the
# project's virtualenv, see api/README.md). Skip this module in that case
# instead of failing the collection of the whole test directory.
pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from api.routers.program_files import WriteContentRequest, write_file_content  # noqa: E402


def _write(home, path, content, create=False):
    return write_file_content(
        WriteContentRequest(homeDir=str(home), programName="prog", path=path, content=content, create=create)
    )


def _refused(home, path, create=False):
    with pytest.raises(HTTPException) as excinfo:
        _write(home, path, "x", create)
    return excinfo.value.status_code


def test_without_create_only_an_existing_file_is_written(tmp_path):
    (tmp_path / "notes.txt").write_text("old")

    _write(tmp_path, "notes.txt", "new")

    assert (tmp_path / "notes.txt").read_text() == "new"
    assert _refused(tmp_path, "missing.txt") == 404
    assert not (tmp_path / "missing.txt").exists()


def test_create_writes_a_new_file_with_the_directories_above_it(tmp_path):
    response = _write(tmp_path, "test/data/input.txt", "1 2 3\n", create=True)

    assert (tmp_path / "test" / "data" / "input.txt").read_text() == "1 2 3\n"
    assert [entry.name for entry in response.entries] == ["test"]


def test_create_replaces_a_file_that_exists(tmp_path):
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "greet.bats").write_text("old")

    _write(tmp_path, "test/greet.bats", "new", create=True)

    assert (tmp_path / "test" / "greet.bats").read_text() == "new"


@pytest.mark.parametrize("path", [".debasher/program.json", "test/.hidden", "__exec__/x", "../outside.txt"])
def test_create_keeps_the_guarantees_of_the_panel(tmp_path, path):
    assert _refused(tmp_path / "home", path, create=True) == 400
    assert not (tmp_path / "outside.txt").exists()


def test_create_never_writes_the_generated_script(tmp_path):
    assert _refused(tmp_path, "prog.sh", create=True) == 400
    assert not (tmp_path / "prog.sh").exists()


def test_a_directory_is_never_written(tmp_path):
    (tmp_path / "test").mkdir()

    assert _refused(tmp_path, "test", create=True) == 400
