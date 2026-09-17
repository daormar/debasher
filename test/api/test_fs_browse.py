import pytest
from fastapi import HTTPException

from api.routers.fs_browse import ListDirsRequest, list_dirs


def test_list_dirs_lists_only_subdirectories(tmp_path):
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_file").write_text("not a directory")

    response = list_dirs(ListDirsRequest(path=str(tmp_path)))

    assert response.path == str(tmp_path)
    assert [entry.name for entry in response.entries] == ["a_dir", "b_dir"]


def test_list_dirs_reports_parent(tmp_path):
    child = tmp_path / "child"
    child.mkdir()

    response = list_dirs(ListDirsRequest(path=str(child)))

    assert response.parent == str(tmp_path)


def test_list_dirs_defaults_to_home_when_path_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("api.routers.fs_browse.Path.home", lambda: tmp_path)

    response = list_dirs(ListDirsRequest(path=""))

    assert response.path == str(tmp_path)


def test_list_dirs_rejects_non_directory(tmp_path):
    a_file = tmp_path / "a_file"
    a_file.write_text("not a directory")

    with pytest.raises(HTTPException) as exc_info:
        list_dirs(ListDirsRequest(path=str(a_file)))

    assert exc_info.value.status_code == 400


def test_list_dirs_excludes_files_by_default(tmp_path):
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_file.sh").write_text("#!/bin/bash\n")

    response = list_dirs(ListDirsRequest(path=str(tmp_path)))

    assert [(entry.name, entry.type) for entry in response.entries] == [("a_dir", "dir")]


def test_list_dirs_includes_files_when_requested(tmp_path):
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_file.sh").write_text("#!/bin/bash\n")
    (tmp_path / "b_file.txt").write_text("text")

    response = list_dirs(ListDirsRequest(path=str(tmp_path), includeFiles=True))

    assert [(entry.name, entry.type) for entry in response.entries] == [
        ("a_dir", "dir"),
        ("a_file.sh", "file"),
        ("b_file.txt", "file"),
    ]


def test_list_dirs_filters_files_by_extension(tmp_path):
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "a_file.sh").write_text("#!/bin/bash\n")
    (tmp_path / "b_file.txt").write_text("text")

    response = list_dirs(
        ListDirsRequest(path=str(tmp_path), includeFiles=True, extensions=[".sh"])
    )

    assert [(entry.name, entry.type) for entry in response.entries] == [
        ("a_dir", "dir"),
        ("a_file.sh", "file"),
    ]
