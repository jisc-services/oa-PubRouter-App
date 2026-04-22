# -*- coding: robot -*-

*** Settings ***
Documentation   Testing whether the correct accounts show up in the manage pages
Resource        resource.robot
Test Setup      Start Test With Admin Login
Test Teardown   Run Keywords  Delete Account Test Data
...             AND  Close Browser

*** Test Cases ***
All Users On Manage
    Create Test Repository
    Go To Manage Page
    Page Should Contain  repo_email@email.com

Only Publishers On Publisher List
    Create Test Repository
    Create Test Publisher
    Go To Manage Page  publishers
    Page Should Contain  publisher_email@email.com
    Page Should Not Contain  repo_email@email.com

Only Repositories On Test Repository List
    Create Test Repository
    Create Test Publisher
    Go To Manage Page  test-repositories
    Page Should Contain  repo_email@email.com
    Page Should Not Contain  publisher_email@email.com

No Test Repositories In Live Repository List
    Create Test Repository
    Go To Manage Page  repositories
    Page Should Not Contain  repo_email@email.com

On Off Button Works On Users Page
    Create Test Repository
    Go To Manage Page
    Wait Until Element With Class Is Visible  acc-okay
    Page Should Not Contain Element With Class  acc-off
    Click Element  css:span.toggle-on-off
    Wait Until Element With Class Is Visible  acc-off
    Page Should Not Contain Element With Class  acc-okay
