#!/bin/sh

test_description='test rebase --interactive'

. ./test-lib.sh


test_expect_success 'Initialize StGit stack' '
    stg init &&
    stg new p0 -m p0 &&
    stg new p1 -m p1 &&
    stg new p2 -m p2 &&
    stg new p3 -m p3
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep p0\nkeep p1\n# --- APPLY_LINE ---\nkeep p2\nkeep p3" >"$1"
	EOF
'
test_expect_success 'Apply patches with APPLY_LINE' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    test "$(stg series --applied -c)" = "2" &&
    git diff-index --quiet HEAD
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "# --- APPLY_LINE ---this_text_does_not_belong" >"$1"
	EOF
'
test_expect_success 'Bad APPLY_LINE throws an error' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    command_error stg rebase --interactive 2>&1 |
    grep -e "Bad APPLY_LINE"
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep p0\nkeep p1" >"$1"
	EOF
'
test_expect_success 'Apply patches without APPLY_LINE' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    test "$(stg series --applied -c)" = "2" &&
    git diff-index --quiet HEAD
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep" >"$1"
	EOF
'
test_expect_success 'Bad todo line throws error' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    command_error stg rebase --interactive 2>&1 |
    grep -e "Bad todo line"
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep invalid_patch_name" >"$1"
	EOF
'
test_expect_success 'Bad patch name throws error' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    command_error stg rebase --interactive 2>&1 |
    grep -e "Bad patch name"
'

test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "invalid_instruction p1" >"$1"
	EOF
'
test_expect_success 'Bad instruction throws error' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    command_error stg rebase --interactive 2>&1 |
    grep -e "Unknown instruction"
'

test_expect_success 'Setup stgit stack' '
    stg new p4 -m p4
'
test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\eof
	echo "delete p4" >"$1"
	eof
'
test_expect_success 'Delete a patch' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    test "$(stg series -c)" = "4" &&
    git diff-index --quiet HEAD
'

test_expect_success 'Setup stgit stack' '
    stg delete $(stg series --all --noprefix --no-description) &&
    stg new -m p0 &&
    stg new -m p1 &&
    stg new -m p2 &&
    stg new -m p3
'
test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\eof
	echo "delete p0\ndelete p2" >"$1"
	eof
'
test_expect_success 'Delete two patches and the correct two are deleted' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    test "$(echo $(stg series --noprefix))" = "p1 p3" &&
    git diff-index --quiet HEAD
'

test_expect_success 'Setup stgit stack' '
    stg delete $(stg series --all --noprefix --no-description) &&
    stg new -m p0 &&
    stg new -m p1
'
test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep p0\nsquash p1" >"$1"
	EOF
'
test_expect_success 'Squash succeeds' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    git diff-index --quiet HEAD &&
    test "$(stg series -c)" = "1"
'

test_expect_success 'Setup stgit stack' '
    stg delete $(stg series --all --noprefix --no-description) &&
    stg new -m p0 &&
    stg new -m p1 &&
    stg new -m p2
'
test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep p0\nsquash p1\nsquash p2" >"$1"
	EOF
'
test_expect_success 'Squash on a Squash succeeds' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    git diff-index --quiet HEAD &&
    test "$(stg series -c)" = "1"
'

test_expect_success 'Setup stgit stack' '
    stg delete $(stg series --all --noprefix --no-description) &&
    stg new -m p0 &&
    stg new -m p1 &&
    stg new -m p2 &&
    stg new -m p3 &&
    stg new -m p4 &&
    stg new -m p5
'
test_expect_success 'Setup fake editor' '
	write_script fake-editor <<-\EOF
	echo "keep p0\nsquash p1\nsquash p2\nkeep p3\nsquash p4\nkeep p5" >"$1"
	EOF
'
test_expect_success 'Two independent squash chains succeed' '
    test_set_editor "$(pwd)/fake-editor" &&
    test_when_finished test_set_editor false &&
    stg rebase --interactive &&
    git diff-index --quiet HEAD &&
    test "$(stg series -c)" = "3"
'

test_expect_success 'No patches exits early' '
    stg delete $(stg series --all --noprefix --no-description) &&
    stg rebase --interactive
'


test_done
