# -*- coding: robot -*-

*** Settings ***
Documentation   Checks admin only functions - whether they can be accessed by admins, etc.
Resource        resource.robot
Test Setup      Run Keywords  Start Test With Admin Login
...             AND  Go To Webservice Page
Test Teardown   Run Keywords  Reset Harvester Data
...             AND  Close Browser

*** Test Cases ***

Can Edit A Harvester Webservice
    Edit Harvester Webservice  EPMC
    Location Should Contain  manage

Start Date Must Be A Date
    Fill Webservice Form
    Input Start Date  This is not a date
    Submit Webservice
    Webservice-manage-page-shown
    Page Should Contain  Date is wrong: time data

Wait Window Must Be Numeric
    Fill Webservice Form
    Input Wait Window  This is not numeric
    Submit Webservice
    Webservice-manage-page-shown
    Page Should Contain  Not a valid integer

Add A Harvester Webservice
    Fill Webservice Form And Submit
    Webservice-manage-page-shown
    Page Should Contain  Record saved
    Page Should Contain  Other EPMC

Can Delete A Harvester Webservice
    Fill Webservice Form And Submit
    Webservice-manage-page-shown
    Click Element  id:delete
    Handle Alert
    Webservices-list-page-shown
    Page Should Contain  Record deleted