#!/usr/bin/env python
from send_test_sword_deposit import run
"""
This script is used to make test SWORDv2 submissions.
"""

# Development environment
# user_name = "be025e0d003e49689141997eceef6339"
# pwd = "b67908f8-21f5-44ec-8e8d-d0459c13882f"
# sword_base_url = "http://localhost:5990/sword2"


user_name = "cca8b3526c784041a32b4d2113cd4ec9"
pwd = "5031f800-81d1-4e49-9062-d7073beeb1ae"
sword_base_url = "https://XXXX.jisc.ac.uk/sword2"
em_iri = "https://XXXX.jisc.ac.uk/sword2/collections/cca8b3526c784041a32b4d2113cd4ec9/170/media"
# in_prog = True
in_prog = False
# em_iri = "http://localhost:5990/sword2/collections/be025e0d003e49689141997eceef6339/1897130/media"
# xml_file = "C:\\Users\\Adam.Rehin\\Jisc\\OA Development - 3.1 UAT testing\\Release 13.3\\R13.3-2-auth-aff-nl\\R13.3-2-auth-aff-nl.xml"
binary_file = "C:\\Users\\Adam.Rehin\\Jisc\\OA Development - 3.1 UAT testing\\Release 13.3\\R13.3-2-auth-aff-nl\\R13.3-2.pdf"
zip_file = "C:\\Users\\Adam.Rehin\\Jisc\\OA Development - 3.1 UAT testing\\Release 13.3\\R13.3-2-auth-aff-nl.zip"

em_iri = None
# binary_file = None
xml_file = None
zip_file = None

# run(sword_base_url, user_name, pwd, xml_file, binary_file, zip_file, in_prog)
run(sword_base_url, user_name, pwd, xml_file, binary_file, zip_file,
    in_prog, em_iri)
