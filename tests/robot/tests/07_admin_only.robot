# -*- coding: robot -*-

*** Settings ***
Documentation   Checks admin only functions - whether they can be accessed by admins, etc.
Resource        resource.robot
Test Setup      Run Keywords  Start Test With Admin Login
...             AND  Create And Manage Repository User
Test Teardown   Run Keywords  Delete Account Test Data
...             AND  Delete Identifier Test Data
...             AND  Close Browser

*** Test Cases ***
Fuzzy Search Shows Search Results
    Create Test Identifiers
    Focus Jisc Identifiers And Enter Text  bad search
    Run Keyword And Expect Error  *  Wait For Jisc Identifier Search Box
    Clear Jisc Identifiers
    Focus Jisc Identifiers And Enter Text  univers
    Wait For Jisc Identifier Search Box

Fuzzy Search Clears If No Option Selected
    Create Test Identifiers
    Focus Jisc Identifiers And Enter Text  bad search
    Set Focus To Element  core_id
    Page Should Not Contain  bad search

Fuzzy Search Is Filled When Option Is Selected
    Create Test Identifiers
    Page Should Not Contain Element With Value  University of Nowhere
    Enter Text For Jisc Identifiers And Select Option  Univers
    Page Should Contain  University of Nowhere
    Click Element By Text  Update all identifiers
    Wait Until Page Contains  Identifiers have been updated.
    Page Should Contain Element With Value  University of Nowhere

Can Load Identifiers
    Go To Admin Panel Page
    Load Identifiers
    Wait Until Page Contains  Successfully uploaded new identifiers for type JISC

Normal User Does Not Have Access To Identifier Search
    Page Should Contain  Admin only account management
    Login Repository User
    Run Keyword And Expect Error  *  Page Should Contain  Admin only account management

Report Page Is Accessible
    Go To Reports Page
    Location Should Contain  reports
    Page Should Contain  Reports
