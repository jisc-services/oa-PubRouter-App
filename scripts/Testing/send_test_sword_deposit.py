#!/usr/bin/env python
"""
This script is used to make test SWORDv2 submissions.
"""
from os import path
import argparse
from sword2.client import SwordClient
from sword2.client.util import SwordException
from sword2.models import ErrorDocument
# from sword2.server.views.blueprint import em_iri


def run(sword_base_url, user_name, pwd, xml_file, binary_files, zip_file, in_prog=False, edit_iri_url=None, get_service=None):
    _collection_url = f"{sword_base_url}/collections/{user_name}"
    if not (user_name and pwd and sword_base_url):
        print("\n*** You must provide Username, Pasword & URL.\n")
        exit(0)

    sword_client = SwordClient(_collection_url,
                               auth_credentials={'username': user_name, 'password': pwd},
                               service_document_iri=sword_base_url,
                               timeout=1200     # 20 mins for TESTING
                               )
    if get_service:
        print(f"\n*** Service Doc URL: {sword_base_url}\n    Collection URL: {_collection_url}\n")
        try:
            service_doc = sword_client.get_service_document()
            print("\nSERVICE DOC:\n", service_doc.to_str(pretty=True))
        except SwordException as e:
            print("\nError:", str(e))
            exit(0)

    deposit_receipt = None

    if xml_file:
        with open(xml_file) as f:
            xml_data = f.read()
        deposit_receipt = sword_client.metadata_deposit(xml_data, in_progress=True)
        print("\nDEPOSITED XML:\n", deposit_receipt.to_str(pretty=True))
        if isinstance(deposit_receipt, ErrorDocument):
            exit(1)

    if binary_files:
        for binary_file in binary_files.split(";"):
            binary_file = binary_file.strip()
            _filename = path.basename(binary_file)
            # Open as binary file
            with open(binary_file, "rb") as f:
                if deposit_receipt:
                    deposit_receipt = sword_client.add_file(_filename,
                                                            f,
                                                            deposit_receipt=deposit_receipt,
                                                            in_progress=True
                                                            )
                elif edit_iri_url:
                    deposit_receipt = sword_client.add_file(_filename,
                                                            f,
                                                            em_iri=edit_iri_url,
                                                            in_progress=True
                                                            )
                else:
                    deposit_receipt = sword_client.file_deposit(_filename,
                                                            f,
                                                            in_progress=True
                                                            )
            print(f"\nDEPOSITED FILE ({_filename}):\n", deposit_receipt.to_str(pretty=True))
            if isinstance(deposit_receipt, ErrorDocument):
                exit(1)

    if zip_file:
        _filename = path.basename(zip_file)
        if not _filename.endswith(".zip"):
            print(f"\n*** ERROR: Zipfile ({_filename}) must end with '.zip'.\n")
            exit(0)
        with open(zip_file, "rb") as f:
            if deposit_receipt:
                deposit_receipt = sword_client.add_file(_filename,
                                                        f,
                                                        deposit_receipt=deposit_receipt,
                                                        in_progress=True
                                                        )
            elif edit_iri_url:
                deposit_receipt = sword_client.add_file(_filename,
                                                        f,
                                                        em_iri=edit_iri_url,
                                                        in_progress=True
                                                        )
            else:
                deposit_receipt = sword_client.file_deposit(_filename,
                                                            f,
                                                            packaging=SwordClient.DEFAULT_PACKAGING,
                                                            in_progress=in_prog
                                                            )
        print(f"\nDEPOSITED ZIPFILE ({_filename}):\n", deposit_receipt.to_str(pretty=True))
        if isinstance(deposit_receipt, ErrorDocument):
            exit(1)


    if not in_prog and not zip_file:
        if deposit_receipt:
            deposit_receipt = sword_client.complete_deposit(deposit_receipt=deposit_receipt)
        elif edit_iri_url:
            deposit_receipt = sword_client.complete_deposit(se_iri=edit_iri_url)
        print(f"\nCOMPLETED DEPOSIT:\n", deposit_receipt.to_str(pretty=True))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # set up the argument parser with various different argument options
    parser.add_argument("-u", "--username", help="Repository (endpoint) Username")
    parser.add_argument("-p", "--password", help="Repository (endpoint) Password")
    parser.add_argument("-url", "--url", help="Base SWORD endpoint URL")
    parser.add_argument("-z", "--zipfile", help="File path to zip file (including filename)")
    parser.add_argument("-x", "--xmlfile", help="Entry (metadata) XNL file")
    parser.add_argument("-f", "--filepath", help="File path to binary file (including filename)")
    parser.add_argument("-g", "--geturl", help="URL to GET")
    parser.add_argument("-i", "--in_progress", action="store_true", help="In-progress indicator True or False")
    parser.add_argument("-e", "--edit", help="Edit-IRI URL used for complete deposit (in_progress is False and no files passed)")
    parser.add_argument("-s", "--service", help="Get service doc")


    args = parser.parse_args()
    service = args.service
    user_name = args.username
    pwd = args.password
    sword_base_url = args.url
    edit_iri_url = args.edit
    if not sword_base_url.startswith("http"):
        sword_base_url = "https://" + sword_base_url

    in_prog = args.in_progress or False
    xml_file = args.xmlfile
    binary_file = args.filepath
    zip_file = args.zipfile

    run(sword_base_url, user_name, pwd, xml_file, binary_file, zip_file, in_prog, edit_iri_url, service)

