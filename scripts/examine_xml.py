"""
Loads a JATS XML file from ZIP & prints key info
"""
from lxml import etree
from os import path
from octopus.core import initialise
from router.jper import packages
from router.jper.app import app     # need to import app_decorator as other modules import it from here.

DIR="C:/Users/Adam.Rehin/Downloads"
FILENAMES = ["test-pkg-no-nsC.zip", "test-pkg-no-nsB.zip", "test-pkg-no-nsA.zip", "rsifv22i233sid364000.zip", "test-pkg-no-ns1.zip", "test-pkg-no-ns2.zip", "test-pkg-no-ns3.zip"]
FILE_JATS_PACKAGE = "https://pubrouter.jisc.ac.uk/FilesAndJATS"


with app.app_context():

    initialise()
    for filename in FILENAMES:
        file_path = path.join(DIR, filename)
        if filename.endswith("zip"):
            zp = file_path
            mf = None
        else:
            zp = None
            mf = [("filesandjats_jats.xml", open(file_path, "rb"))]
        pkg_handler = packages.PackageFactory.get_pkg_mgr_and_extract_metadata_from_file(
            FILE_JATS_PACKAGE, zip_path=zp, metadata_files=mf)
        xml = pkg_handler.jats.xml
        xml_str = etree.tostring(xml, encoding="unicode", pretty_print=True)
        print("\n-----------\n", filename, "--\n", xml_str)
        md = pkg_handler.notification_metadata()
