import pytest

# The router under test imports fastapi, which the system Python used by
# `make check` may not have (the API's own requirements live in the
# project's virtualenv, see api/README.md). Skip this module in that case
# instead of failing the collection of the whole test directory.
pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from api.routers.program_files import (  # noqa: E402
    DeleteRequest,
    MoveRequest,
    WriteContentRequest,
    delete_entry,
    move_entry,
    write_file_content,
)


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


# --- deleting and moving ------------------------------------------------------


@pytest.fixture
def layout(tmp_path):
    """A home directory with a test file, a link to a directory inside it and
    a link to a directory outside it, which holds a file of its own."""
    home = tmp_path / "home"
    (home / "test" / "data").mkdir(parents=True)
    (home / "test" / "data" / "in.txt").write_text("data")
    (home / ".debasher").mkdir()
    (home / ".debasher" / "program.json").write_text("{}")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("not the program's")
    (home / "link_in").symlink_to("test/data")
    (home / "link_out").symlink_to(outside)
    return home, outside


def _delete(home, path):
    return delete_entry(DeleteRequest(homeDir=str(home), programName="prog", path=path))


def _move(home, src, dst):
    return move_entry(MoveRequest(homeDir=str(home), programName="prog", srcPath=src, dstPath=dst))


def _status(call):
    with pytest.raises(HTTPException) as excinfo:
        call()
    return excinfo.value.status_code


@pytest.mark.parametrize(
    "path",
    ["../outside/victim.txt", "link_out/victim.txt", ".debasher", ".debasher/program.json", ".", "test/..", ""],
)
def test_nothing_outside_the_home_directory_or_reserved_is_deleted(layout, path):
    home, outside = layout

    assert _status(lambda: _delete(home, path)) == 400

    assert (outside / "victim.txt").exists()
    assert (home / ".debasher" / "program.json").exists()
    assert (home / "test" / "data" / "in.txt").exists()


def test_an_absolute_path_is_never_deleted(layout):
    home, outside = layout

    assert _status(lambda: _delete(home, str(outside / "victim.txt"))) == 400
    assert (outside / "victim.txt").exists()


def test_deleting_a_link_removes_the_link_not_what_it_points_to(layout):
    home, outside = layout

    _delete(home, "link_in")
    _delete(home, "link_out")

    assert not (home / "link_in").is_symlink()
    assert not (home / "link_out").is_symlink()
    assert (home / "test" / "data" / "in.txt").read_text() == "data"
    assert (outside / "victim.txt").exists()


def test_a_link_that_points_nowhere_can_be_deleted(layout):
    home, _ = layout
    (home / "dangling").symlink_to("nowhere")

    _delete(home, "dangling")

    assert not (home / "dangling").is_symlink()


def test_a_directory_is_deleted_with_what_it_holds(layout):
    home, _ = layout

    _delete(home, "test")

    assert not (home / "test").exists()


@pytest.mark.parametrize(
    "src, dst",
    [
        ("test/data/in.txt", "../outside/stolen.txt"),
        ("../outside/victim.txt", "test/victim.txt"),
        ("link_out/victim.txt", "test/victim.txt"),
        ("test/data/in.txt", ".debasher/in.txt"),
        (".", "elsewhere"),
    ],
)
def test_nothing_is_moved_out_of_or_into_the_home_directory(layout, src, dst):
    home, outside = layout

    assert _status(lambda: _move(home, src, dst)) == 400

    assert sorted(p.name for p in outside.iterdir()) == ["victim.txt"]
    assert (home / "test" / "data" / "in.txt").exists()


def test_moving_a_link_moves_the_link_not_what_it_points_to(layout):
    home, _ = layout

    _move(home, "link_in", "test/link")

    assert (home / "test" / "link").is_symlink()
    assert not (home / "link_in").is_symlink()
    assert (home / "test" / "data" / "in.txt").read_text() == "data"


def test_a_move_never_replaces_an_entry_not_even_a_link(layout):
    home, _ = layout
    (home / "test" / "other.txt").write_text("other")

    assert _status(lambda: _move(home, "test/other.txt", "link_in")) == 400
    assert (home / "test" / "other.txt").read_text() == "other"
