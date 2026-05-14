# -*- coding: robot -*-

*** Settings ***
Documentation   Checks whether the forms on repository config are functional.
Resource        resource.robot
# Test Setup      Run Keywords  Start Test With Admin Login
# ...             AND  Create And Login Repository User
# Test Teardown   Run Keywords  Delete Account Test Data
# ...             AND  Close Browser
Test Teardown   Run Keywords  Close Browser

*** Test Cases ***
Begin Create Repo User
    Start Test With Admin Login
    Create And Login Repository User

Bad Matching Params
    Open Login Repository
    Go To Account Config Page
    Upload Bad Matching Params
    Page Should Contain  Please check that your file is in CSV format

Invalid Matching Params
    Open Login Repository
    Go To Account Config Page
    Upload Invalid Matching Params
    Page Should Contain  Please check that your file is in CSV format

Good Matching Params
    Open Login Repository
    Go To Account Config Page
    Upload Good Matching Params
    Page Should Contain  Your matching parameters have been updated
    Page Should Contain  .+

Matching Params No Flash Text
    Open Login Repository
    Go To Account Config Page
    Upload Good Matching Params
    Page Should Not Contain  Some redundant match parameters were removed during upload

Matching Params Flash Text
    Open Login Repository
    Go To Account Config Page
    Upload Good Duplicate Matching Params
    Page Should Contain  Some redundant match parameters were removed during upload
    Click Element By Text  Some redundant match parameters were removed during upload
    Wait Until Page Contains  Below, is a list of the redundant parameters removed
    Page Should Contain  the university of example
    Page Should Contain  bad.example.ac.uk

End Delete Repo Account
    Delete Account Test Data
