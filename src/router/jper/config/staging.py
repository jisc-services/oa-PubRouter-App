"""
Staging (UAT / Pre-production) environment configuration file for the JPER application

On deployment, configuration can be overridden by using a local ~/.pubrouter/jper.cfg file
"""
PUB_TEST_EMAIL_ADDR = {
    True: ["XXXX.YYYY@YYYY.ac.uk", "ZZZZ@YOUR-ORG.ac.uk"],
    False: ["XXXX.YYYY@YYYY.ac.uk", "ZZZZ@YOUR-ORG.ac.uk"],
}
