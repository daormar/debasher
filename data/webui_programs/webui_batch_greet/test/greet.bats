# Process tests of webui_batch_greet: the business logic of its process
# greet, run on its own with debasher_test

load "${DEBASHER_BATS_HELPERS}"

@test "greet writes the greeting into its file" {
    run debasher_process greet -text Ann -secs 0 \
        -outf "${BATS_TEST_TMPDIR}/greeting.txt"
    [ "${status}" -eq 0 ]
    [ "$(cat "${BATS_TEST_TMPDIR}/greeting.txt")" = "Hello, Ann!" ]
}

@test "greet fails on the text fail, and writes no greeting" {
    run --separate-stderr debasher_process greet -text fail -secs 0 \
        -outf "${BATS_TEST_TMPDIR}/greeting.txt"
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "Error: asked to fail" ]
    [ ! -e "${BATS_TEST_TMPDIR}/greeting.txt" ]
}
