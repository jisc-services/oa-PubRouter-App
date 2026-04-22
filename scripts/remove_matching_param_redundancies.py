#!/usr/bin/env python

"""
Script for removing redundancies in all current live repository configurations' matching parameters 
"""

from router.shared.models.account import AccRepoMatchParams
from router.jper.app import app

with app.app_context():
    for repo_config in AccRepoMatchParams.pull_all(for_update=True):
        # remove redundant match params
        redundancy_messages = repo_config.remove_redundant_matching_params_and_sort()
        if redundancy_messages:
            # print list of redundancies together with which repository they came from
            print(f"*** Repository ID: {repo_config.id}")
            for message in redundancy_messages:
                print(message)
            # (manually) check the output before making an actual save to the repository
            if input("Is this ok? Press enter if so, enter anything else to skip\n") == "":
                # save if we changed something and print something to terminal to inform script user what happened
                # will skip this repository from saving if anything other than the empty string is entered
                repo_config.update()
