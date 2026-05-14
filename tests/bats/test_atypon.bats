#!/usr/bin/env bats
# NOTE: This file MUST be executed from the BASE pubrouter directory, aka the directory above this one.
# View main README.md for explanation about BATS
function setup() {
    export MAIN_DIR="$(mktemp -d)"
    export USERNAME="$(whoami)"
    export TEMP_DIR="$MAIN_DIR/ftptmp"
    export TMP_ARCHIVE="$MAIN_DIR/tmparchive"
    export ZIP_DIR="$MAIN_DIR/$USERNAME"
    mkdir $TEMP_DIR
    mkdir $TMP_ARCHIVE
    mkdir $ZIP_DIR
    export UNIQUE_ID="doesnotneedtobeunique"
}

function teardown() {
    if [ $BATS_TEST_COMPLETED ]; then
        rm -rf "$MAIN_DIR"
    else
        echo "Test failed, not deleting test directory"
        echo "Test directory is located at $MAIN_DIR"
    fi
}

move_script="./deployment/moveAtyponFTPfiles.sh"

@test "Should return error if given file is not a zip" {
    file_loc="$ZIP_DIR/notazip"
    mkdir $file_loc
    run $move_script $USERNAME $USERNAME $TEMP_DIR $UNIQUE_ID $file_loc $TMP_ARCHIVE

    file_count=$(ls "$TMP_ARCHIVE/$USERNAME/$UNIQUE_ID" | wc -l)
    # Will fail as the unzip command will fail
    [ "$status" -eq 1 ]
    [ "$file_count" -eq 1 ]

    # Make sure file was removed
    run ls $file_loc
    [ "$status" -ne 0 ]
}

@test "Should return error if bad zip is given" {
    file_loc="$ZIP_DIR/bad_zip.zip"
    cp "./bats/resources/bad_zip.zip" $file_loc
    run $move_script $USERNAME $USERNAME $TEMP_DIR $UNIQUE_ID $file_loc $TMP_ARCHIVE

    file_count=$(ls "$TMP_ARCHIVE/$USERNAME/$UNIQUE_ID" | wc -l)
    # Will fail because there was no files to unzip
    [ "$status" -eq 1 ]
    [ "$file_count" -eq 1 ]

    # Make sure file was removed
    run ls $file_loc
    [ "$status" -ne 0 ]
}

@test "Should be successful if there are any directories in the zip file" {
    file_loc="$ZIP_DIR/good_zip.zip"
    cp "./bats/resources/good_zip.zip" $file_loc
    run $move_script $USERNAME $USERNAME $TEMP_DIR $UNIQUE_ID $file_loc $TMP_ARCHIVE

    file_count=$(ls "$TMP_ARCHIVE/$USERNAME/$UNIQUE_ID" | wc -l)
    [ "$status" -eq 0 ]
    # Should be three ID files and the original zip file
    [ "$file_count" -eq 4 ]

    # Find all created note zip files, and return only the filename (excluding directory path)
    note_file_paths=$(find "$TEMP_DIR" -type f)
    # Should have three note files.
    [ "$(echo "$note_file_paths" | wc -l)" -eq 3 ]

    echo $output
    # Check for each note zip file - should be note_1.zip, note_2.zip, note_3.zip.
    for file in $note_file_paths; do
        # match note_(DIGIT).zip
        [[ $(stat -c "%U" "$file") = "$USERNAME" ]]
        [[ "$(basename "$file")" =~ note_[0-9]\.zip ]]
    done

    # Make sure file was removed
    run ls $file_loc
    [ "$status" -ne 0 ]
}

@test "Should be successful if the zip has spaces in" {
    file_loc="$ZIP_DIR/good zip with spaces.zip"
    cp "./bats/resources/good_zip.zip" "$file_loc"
    run $move_script $USERNAME $USERNAME $TEMP_DIR $UNIQUE_ID "$file_loc" $TMP_ARCHIVE

    echo "$output"

    file_count=$(ls "$TMP_ARCHIVE/$USERNAME/$UNIQUE_ID" | wc -l)
    [ "$status" -eq 0 ]
    # Should be three ID files and the original zip file
    [ "$file_count" -eq 4 ]

    # Find all created note zip files, and return only the filename (excluding directory path)
    note_file_paths=$(find "$TEMP_DIR" -type f)
    # Should have three note files.
    [ "$(echo "$note_file_paths" | wc -l)" -eq 3 ]

    # Check for each note zip file - should be note_1.zip, note_2.zip, note_3.zip.
    for file in $note_file_paths; do
        # match note_(DIGIT).zip
        [[ $(stat -c "%U" "$file") = "$USERNAME" ]]
        [[ "$(basename "$file")" =~ note_[0-9]\.zip ]]
    done

    # Make sure file was removed
    run ls $file_loc
    [ "$status" -ne 0 ]
}

@test "Should be successful if the folders inside the zip have spaces" {
    file_loc="$ZIP_DIR/good_zip_spaces_inside_folders.zip"
    cp "./bats/resources/good_zip.zip" "$file_loc"
    run $move_script $USERNAME $USERNAME $TEMP_DIR $UNIQUE_ID "$file_loc" $TMP_ARCHIVE

    echo "$output"

    file_count=$(ls "$TMP_ARCHIVE/$USERNAME/$UNIQUE_ID" | wc -l)
    [ "$status" -eq 0 ]
    # Should be three ID files and the original zip file
    [ "$file_count" -eq 4 ]

    # Find all created note zip files, and return only the filename (excluding directory path)
    note_file_paths=$(find "$TEMP_DIR" -type f)
    # Should have three note files.
    [ "$(echo "$note_file_paths" | wc -l)" -eq 3 ]

    # Check for each note zip file - should be note_1.zip, note_2.zip, note_3.zip.
    for file in $note_file_paths; do
        # match note_(DIGIT).zip
        [[ $(stat -c "%U" "$file") = "$USERNAME" ]]
        [[ "$(basename "$file")" =~ note_[0-9]\.zip ]]
    done

    # Make sure file was removed
    run ls $file_loc
    [ "$status" -ne 0 ]
}