# -*- coding: robot -*-

*** Settings ***
Documentation   Checks whether the forms for publishers are functional.
Resource        resource.robot
Test Setup      Run Keywords  Start Test With Admin Login
...             AND  Create And Login Publisher User
Test Teardown   Run Keywords  Delete Account Test Data
...             AND  Close Browser

*** Test Cases ***
# TEST BROKEN ON SERVER
# Embargo Is Not Numeric
#    Set Embargo Duration  aardvark
#    Update Embargo License
#    Wait Until Page Contains  Not a valid integer value. Please enter number of months (integer value)

Valid Embargo and License
    Set Embargo Duration  6
    Set Licence URL  http://somelicence.com
    Update Embargo License
    Wait Until Page Contains  Your defaults have been updated.
    Page Should Contain Element  css:#embargo_duration[value="6"]
    Page Should Contain Element  css:#license_url[value="http://somelicence.com"]


