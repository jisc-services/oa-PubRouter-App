# -*- coding: robot -*-

*** Settings ***
Documentation   Checks whether the forms for repositories are functional.
Resource        resource.robot
# Force Tags      crashing

# Test Setup      Run Keywords  Start Test With Admin Login
# ...             AND  Create And Login Repository User
# Test Teardown   Run Keywords  Delete All Test Data
# ...             AND  Close Browser
Test Teardown   Run Keywords  Close Browser

*** Test Cases ***
Begin Create Repo User
    Start Test With Admin Login
    Create And Login Repository User

Non Numeric Max Pub Age
    Login Repository User Click Sword
    Set Max Pub Age  This is not a number
    Page Should Contain  Maximum age must be an integer between 1 and 100, or blank.

Negative Max Pub Age
    Login Repository User Click Sword
    Set Max Pub Age  -1
    Page Should Contain  Maximum age must be an integer between 1 and 100, or blank.

Valid Max Pub Age
    Login Repository User Click Sword
    Set Max Pub Age  1
    Page Should Contain  Successfully updated maximum age
    Pub Age Should Be  1

# TEST DOESN'T WORK ON SERVER
# Eprints Deposit Location Should Hide With DSpace
#     Login Repository User Click Sword
#     Select Repository XML Format  eprints
#     Wait Until Element Is Visible  id:uniform-target_queue
#     Select Repository XML Format  dspace
#     Wait Until Element Is Not Visible  id:uniform-target_queue
#     Select Repository XML Format  eprints
#     Wait Until Element Is Visible  id:uniform-target_queue

#Packaging Preferences Should Hide With Eprints RIOXX
#    Login Repository User Click Sword
#    Element Should Be Visible  packaging
#    Select Repository XML Format  eprints-rioxx
#    Element Should Not Be Visible  packaging

# DISABLED - Has some odd problem with chromedriver that makes it not work properly.
#Go Live
#    Login Repository User Click Sword
#    Element Should Not Be Visible  golive
#    Go Live On Repository
#    Wait Until Page Contains  LIVE status

Notification Sources None Button Should Untick All
    Login Repository User Click Sword
    All Checkboxes Should Be Ticked
    Uncheck And Save All Sources
    Page Should Contain  Your notification sources have been saved
    All Checkboxes Should Be Unticked

Notification Sources All Button Should Tick All
    Login Repository User Click Sword
    Uncheck And Save All Sources
    All Checkboxes Should Be Unticked
    Check And Save All Sources
    Page Should Contain  Your notification sources have been saved
    All Checkboxes Should Be Ticked

# Invalid Email
#    Login Repository User Click Sword
#    Update Contact Email  not an email
#    Wait Until Page Contains  Contact email not updated: Invalid email address.

Valid User Details
    Login Repository User Click Sword
    Update User Details  other_text  other_note  email@email.com
    Page Should Contain  Account settings updated
    Account Org Name Should Be  other_text
    Note Should Be  other_note
    Contact Email Should Be  email@email.com

End Delete Repo Account
    Delete Account Test Data
