from api.markdown_parsing import function_header_name, split_function_blocks


def test_split_function_blocks_returns_a_single_block_when_there_are_no_helpers():
    code = "generate ()\n{\n    :\n}"

    assert split_function_blocks(code) == [code]


def test_split_function_blocks_splits_a_helper_and_its_caller_apart():
    # Mirrors debasher::_show_proc_implem_bash_func's own output shape:
    # same-script helpers first, the process's own exec function last,
    # each block blank-line separated.
    helper_block = "count_chars ()\n{\n    :\n}"
    exec_block = "count ()\n{\n    count_chars\n}"
    code = f"{helper_block}\n\n{exec_block}"

    assert split_function_blocks(code) == [helper_block, exec_block]


def test_split_function_blocks_returns_no_blocks_for_empty_code():
    assert split_function_blocks("") == []


def test_function_header_name_reads_the_first_lines_function_name():
    assert function_header_name("count_chars ()\n{\n    :\n}") == "count_chars"


def test_function_header_name_returns_none_for_empty_source():
    assert function_header_name("") is None


def test_parse_proc_info_markdown_reads_the_task_shaping_options_apart():
    from api.markdown_parsing import parse_proc_info_markdown

    info = parse_proc_info_markdown(
        "## worker\n"
        "\n"
        "### Process Options\n"
        "- `-id` <int> id of writer \n"
        "\n"
        "### Task Shaping Options\n"
        "Read only to define the tasks of the process; the process function does not receive them.\n"
        "- `-w` <int> Number of workers. (command-line,mandatory)\n"
    )

    options = {option.label: option for option in info.options}
    assert not options["-id"].taskShaping
    assert options["-w"].taskShaping
    assert options["-w"].commandLine and options["-w"].mandatory
    assert options["-w"].dataType == "int"
    assert options["-w"].description == "Number of workers."
