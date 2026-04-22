#!/bin/bash

## Script to recursively produce zip archives of nested Git repositories.
SCRIPT='C:/_GIT/GitHub/jisc-services/oa-PubRouter-App-Public/archive_git_repos_as_zips.sh'
ZIP_DIR="C:/_GIT/GitHub/jisc-services/SOURCE-oa-PubRouter-App-Public"
PWD=`pwd`
THIS=`basename "$PWD"`
ZIP_FILE="$ZIP_DIR/${THIS}.zip"

echo -e "\nCreating: $ZIP_FILE"
git archive -o "$ZIP_FILE" HEAD

git submodule --quiet foreach "$SCRIPT"


# end #
