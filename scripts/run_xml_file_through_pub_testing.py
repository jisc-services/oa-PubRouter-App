"""
Run a JATS XML file through publisher testing - you can change following global variable values as needed. They are
currently set assuming the script is run in development & XML file is in Downloads directory:

    XML_FILENAME = "copernicus-sample.xml"
    DIR="C:/Users/Adam.Rehin/Downloads"

    PUB_TYPE_U_OR_B = ARTICLES_UPON_PUBLICATION
    PUB_DEFAULT_LICENCE_URL = None
    PUB_DEFAULT_EMBARGO_MONTHS = None
    ROUTE_NOTE_AFTER_VALIDATION = False
"""
from os import path
from zipfile import ZipFile
from octopus.core import initialise
from router.jper.web_main import app
from router.jper.pub_testing import init_pub_testing
from router.jper.validate_route import auto_testing_validation_n_routing
from tests.fixtures.factory import AccountFactory

ARTICLES_UPON_PUBLICATION = "u"
ARTICLES_BEFORE_PUBLICATION = "b"
FILE_JATS_PACKAGE = "https://pubrouter.jisc.ac.uk/FilesAndJATS"

### VALUES TO CHANGE AS NEEDED ###

XML_FILENAME = "copernicus-sample.xml"
DIR="C:/Users/Adam.Rehin/Downloads"

PUB_TYPE_U_OR_B = ARTICLES_UPON_PUBLICATION
PUB_DEFAULT_LICENCE_URL = None
PUB_DEFAULT_EMBARGO_MONTHS = None
ROUTE_NOTE_AFTER_VALIDATION = False

def create_pub_acc(test_type="u", default_licence_url=None, embargo_months=None, route_note=False):
    """
    Create publisher account.
    :param test_type: String - "u" - Upon publication or "b" - Before publication
    :param default_licence_url: String - URL of licence
    :param embargo_months: Int - Number of months embargo
    :param route_note: Boolean - True: create & route a notification that passes auto-validation;
                                      False: Don't create/route notification (i.e. validate only)
    :return: publisher account object
    """
    test_type = test_type.lower()
    if test_type not in ["u", "b"]:
        raise Exception(f"Invalid publisher test type '{test_type}', should be one of: ['u', 'b']")
    publisher = AccountFactory.publisher_account()
    publisher.publisher_data.in_test = True
    pub_data = publisher.publisher_data
    pub_data.init_testing()
    pub_data.test_type = test_type
    pub_data.test_start = "2024-01-01"
    pub_data.test_emails = ["adam.rehin@jisc.ac.uk"]
    pub_data.route_note = route_note
    if default_licence_url:
        pub_data.license = {"url": default_licence_url}
    if embargo_months:
        pub_data.embargo = embargo_months
    # Set the publisher to be active
    publisher.status = 1
    publisher.update()
    return publisher


with app.app_context():

    initialise()

    file_path = f"{DIR}/{XML_FILENAME}"
    zip_path = path.splitext(file_path)[0] + '.zip'
    with ZipFile(zip_path, 'w') as myzip:
        myzip.write(file_path, XML_FILENAME)
        myzip.writestr(f"dummy.pdf", "Dummy pdf file")
    basic_note_dict = {
        "vers": app.config.get("API_VERSION"),
        "provider": {"route": "ftp"},
        "content": {"packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"}
    }

    pub_acc = create_pub_acc(PUB_TYPE_U_OR_B, PUB_DEFAULT_LICENCE_URL, PUB_DEFAULT_EMBARGO_MONTHS, ROUTE_NOTE_AFTER_VALIDATION)
    pub_test = init_pub_testing(pub_acc, "ftp", init_mail=True)
    pub_test.set_filename(XML_FILENAME)
    note_id = None
    try:
        note_id = auto_testing_validation_n_routing(pub_test, basic_note_dict, note_zip_file=zip_path)
    except Exception as e:
        print("*** EXCEPTION:\n", repr(e))

    if pub_test.issues:
        print(f"\n*** {pub_test.num_issues()} ISSUES:\n")
        for issue in pub_test.issues:
            print("  *", issue)
    else:
        print("\n*** No issues ***")
    if pub_test.errors:
        print(f"\n*** {pub_test.num_errors()} ERRORS:\n")
        for err in pub_test.errors:
            print("  *", err)
    else:
        print("\n*** No errors ***")
    if note_id:
        print("\n*** Notification ID: ", note_id)
