"""
Production environment configuration file for the JPER application

On deployment, configuration can be overridden by using a local ~/.pubrouter/jper.cfg file
"""
# URL to Router public documentation Github repo
DOCU_BASE_URL = "https://github.com/jisc-services/Public-Documentation/tree/master/PublicationsRouter"
DOCU_API_URL = f"{DOCU_BASE_URL}/api/v4"

# Names of reports to send to particular email addresses
# PUBLIC VERSION: obfuscate details
REPORT_EMAIL_ADDRESSES = {
    'AAAA.XXXX@ZZZZ.ac.uk': ["institutions_live", "institutions_test", "publisher", "harvester", "dup_submission"],
    'BBBB.YYYY@ZZZZ.ac.uk': ["institutions_live", "institutions_test", "publisher", "harvester", "dup_submission"],
    'CCCC.ZZZZ@ZZZZ.ac.uk': ["institutions_live"]
}
# Other report (e.g. Publisher DOI report) BCC list
REPORT_BCC = ["XXXX.YYYY@ZZZZ.ac.uk", "AAAA.YYYY@ZZZZ.ac.uk"]
CONTACT_CC = ["XXXX.YYYY@ZZZZ.ac.uk", "BBBB.YYYY@ZZZZ.ac.uk"]
