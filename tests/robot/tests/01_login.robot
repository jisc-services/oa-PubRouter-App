# -*- coding: robot -*-

*** Settings ***
Documentation   Testing correct login functions
Resource        resource.robot
Test Teardown   Run Keywords  Close Browser

*** Test Cases ***
Login With Valid Credentials
    Open Browser To Login Page
    Decline Cookies
    Input Username  admin
    Input Password  admin
    Submit Credentials
    Admin Account Page Should Be Open

Login With Invalid Credentials
    Open Browser To Login Page
    Decline Cookies
    Input Username  fake
    Input Password  fake
    Submit Credentials
    Login Page Should Be Open
    Current Frame Should Contain  Incorrect username/password

Can Logout
    Start Test With Admin Login
    Logout Current User
    Home Page Should Be Open
    Current Frame Should Contain  You are now logged out
