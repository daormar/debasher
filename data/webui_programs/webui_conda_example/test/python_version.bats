# Process tests of webui_conda_example: the business logic of its process
# python_version, run on its own with debasher_test. They need the conda
# environment py27, which a run with conda support creates, and are
# skipped where it does not exist.

load "${DEBASHER_BATS_HELPERS}"

@test "python_version writes the version of the Python of py27" {
    debasher_skip_without_conda_env py27
    run debasher_process python_version -outf "${BATS_TEST_TMPDIR}/python_version.txt"
    [ "${status}" -eq 0 ]
    [[ "$(cat "${BATS_TEST_TMPDIR}/python_version.txt")" == "Python 2.7."* ]]
}
