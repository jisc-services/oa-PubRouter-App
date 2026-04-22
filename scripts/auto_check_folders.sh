#!/bin/bash

folders=( "/Incoming/ftptmp" "/Incoming/sftpusers" )

function check_empty {
	echo "Folder to check $1" >> daily_check.txt

	for f in $1/*; do
		list=$(ls $f -I xfer | wc -l)
		if [ $list -ne 0 ]; then
			echo "Problem with $f" >> daily_check.txt
		fi
	done
}

echo "Checking if the folders for receiving ftp archives are empty (all files have been processed)" > daily_check.txt

for folder in "${folders[@]}"; do
	check_empty $folder
done

cat daily_check.txt | mail -s "List of ftp users folder" XXXX.YYYY@jisc.ac.uk

exit 0
