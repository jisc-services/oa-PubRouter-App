#!/bin/bash
######################################################################
# Script for sending a package zip file
#
# Params:
#   1. URL endpoint
#   2. API-Key
#   3. Path to zip file
#   4. Filename
######################################################################
echo -e "\n"
URL=${1:-}
echo -e "* URL End-point: $URL."

API_KEY=${2:-}
echo -e "* API Key: $API_KEY."

ZIP_PATH=${3:-}
echo -e "* Zip path: $ZIP_PATH."

FILENAME=${4:-}
echo -e "* Filename: $FILENAME."

[ "$URL" = "" -o "$API_KEY" = "" -o "$ZIP_PATH" = "" -o "$FILENAME" = "" ] && echo -e "\n\nPARAMETER ERROR: URL endpoint, Api-key, zip-path and Filename must ALL be provided.\n" && exit 1

# Write minimal JSON to file
JSON_PATH=./min_json.json
echo -e '{"content" : {"packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"}}' > $JSON_PATH

curl -XPOST \
 -F "metadata=@$JSON_PATH;type=application/json;filename=min_json.json" \
 -F "content=@$ZIP_PATH;type=application/zip;filename=$FILENAME" \
 $URL?api_key=$API_KEY

exit 0
