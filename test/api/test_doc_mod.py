from api.doc_mod import parse_module_markdown


def test_parse_module_markdown_does_not_take_a_module_section_for_a_process():
    # Mirrors debasher_doc_mod's own output shape: module title and
    # description, then the module's own sections, then one section per
    # process.
    markdown = "\n".join(
        [
            "# mymod",
            "",
            "Module description.",
            "",
            "## Program Type",
            "",
            "`resident`",
            "",
            "## Shared Directories",
            "- `data`",
            "",
            "## writer",
            "",
            "### Description",
            "Writes.",
            "",
            "## reader",
            "",
            "### Description",
            "Reads.",
        ]
    )

    name, description, shared_dirs, processes = parse_module_markdown(markdown)

    assert name == "mymod"
    assert description == "Module description."
    assert shared_dirs == ["data"]
    assert [process_name for process_name, _ in processes] == ["writer", "reader"]
    assert "Writes." in processes[0][1]


def test_split_seq_process_chunks_tells_sequential_processes_apart():
    from api.doc_mod import split_seq_process_chunks

    markdown = "\n".join(
        [
            "# mymod",
            "",
            "## worker",
            "### Description",
            "Works.",
            "",
            "## Sequential Process: step",
            "### Description",
            "Steps.",
        ]
    )

    _, _, _, chunks = parse_module_markdown(markdown)
    processes, seq_processes = split_seq_process_chunks(chunks)

    assert [name for name, _ in processes] == ["worker"]
    assert [name for name, _ in seq_processes] == ["step"]
    assert "Steps." in seq_processes[0][1]
