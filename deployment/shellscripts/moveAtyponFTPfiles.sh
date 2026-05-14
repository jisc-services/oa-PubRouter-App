#!/usr/bin/env bash
# CALLING CONVENTION:
#    moveAtyponFTPfiles.sh  username  newowner  target_tmp_dir  unique_id  atypon_file  tmp_archive
#
# This script requires sudo and should expect to have a line such as this added to `/etc/sudoers.d/jenkins`:
# jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/moveAtyponFTPfiles.sh
#
# FUNCTIONALITY:
# Unzips the given atypon zip file located at `atypon_file`. After unzipping the file, it looks for issue
# sub-directories (which will themselves contain article sub-directories and (possibly) a single issue-info sub-directory).
#
# For each issue-directory, list the immediate sub-directories and for each of these, where its name differs from the
# issue directory, zip it up and place it in ftptmp as if it was a single deposit.
#
# Generic Atypon zip structure (although, typically we expect only a single Issue-directory):
#   Top-directory
#         |
#         |--- Issue-directory
#         |           |
#         |           |--- Issue-info-directory (has SAME name as Issue-directory) - we IGNORE this
#         |           |--- Article-directory (may contain sub-directories) - we zip this
#         |           |--- Article-directory (may contain sub-directories) - we zip this
#         |           |--- etc
#         |
#         |--- Issue-directory
#         |           |
#         |           |--- Issue-info-directory (has SAME name as Issue-directory) - we IGNORE this
#         |           |--- Article-directory (may contain sub-directories) - we zip this
#         |           |--- Article-directory (may contain sub-directories) - we zip this
#         |           |--- etc
#
# -------------------------------------------------------------------------
username="$1"
newowner="$2"
# Get the FULL path of the target temp dir otherwise we won't zip the directory to the correct place
target_tmp_dir="$(readlink -f "$3")"
unique_id="$4"
atypon_file="$5"
tmp_archive="$6"

# Self defined shell-script exit codes
BAD_ATYPON_FILE=7           # code returned if problem with Atypon zip file

# Create a zip file and insert it into the tmp folder.
# NOTE: this does not share state (the variables above) when executed, as it's executed in a different shell by find.
create_zip(){
    target_tmp_dir="$1"
    dir_to_zip="$2"
    tmp_archive="$3"
    username="$4"
    atypon_unique_id="$5"
    newowner="$6"
    zip_name="$7"
    
    # Create a UUID for this article directory
    article_uuid=$(sed 's/-//g' /proc/sys/kernel/random/uuid)

    # target_tmp_dir/username
    target_dir="$target_tmp_dir/$username"
    mkdir -p "$target_dir/$article_uuid"

    # Add file in tmp archive to show which article IDs the atypon deposit matches
    touch "$tmp_archive/$username/$atypon_unique_id/article_id_$article_uuid"
    cd "$dir_to_zip"

    # Be quiet when zipping so there's no spam output
    zip_location="$target_dir/$article_uuid/$zip_name.zip"
    zip -rq "$zip_location" "."
    # Chown target directory to ftptmp owner
    chown -R "$newowner":"$newowner" "$target_dir"
};

# Export the function so other shells used by this script can use the create_zip function
export -f create_zip;

# Copy atypon zip file into the tmp archive
archive_location="$tmp_archive/$username/$unique_id"
mkdir -p "$archive_location"
cp -R "$atypon_file" "$archive_location"
# Create empty file indicating this directory holds an atypon file
touch "$archive_location/atypon_file"
# Chown target directory to tmparchive owner
chown -R "$newowner":"$newowner" "$archive_location"

# Get the directory the file is in and make a new directory to store unzipped files in
tmp_unzip_dir="$(dirname "$atypon_file")/$unique_id"
mkdir -p "$tmp_unzip_dir"

article_count=0

# If no problems unzipping Atypon file quietly into directory
if unzip -q -d "$tmp_unzip_dir" "$atypon_file"; then
  # Find all issue directories (each of which contains article directories); process each of these
  for iss_dir in $(find "$tmp_unzip_dir" -maxdepth 1 -mindepth 1 -type d); do
    iss_dir_name=$(basename "$iss_dir")
    # Find all sub-directories immediately below the Issue directory; process each of these
    for dir in $(find "$iss_dir" -maxdepth 1 -mindepth 1 -type d); do
      dir_name=$(basename "$dir")
      # The issue directory may contain a sub-directory of the same name containing issue info, which we want to ignore
      # Otherwise, create a new zip file from the dir found
      if [ "$iss_dir_name" != "$dir_name" ]; then
        create_zip "$target_tmp_dir" "$dir" "$tmp_archive" "$username" "$unique_id" "$newowner" "$dir_name"
        (( article_count += 1 ))
      fi
    done
  done
fi

# Remove leftover files in $tmp_unzip_dir.
# The original atypon file will be located in the tmparchive.
rm -rf "$tmp_unzip_dir"
rm "$atypon_file"

# Either Atypon file couldn't be unzipped or No article directories found
if [[ $article_count -eq 0 ]]; then
    # Exit with error code so python knows this was a bad file
    exit $BAD_ATYPON_FILE
fi

# end #
