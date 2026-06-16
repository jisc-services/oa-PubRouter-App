# -*- coding: robot -*-

*** Settings ***
Documentation   Tests to see if the user creation form works correctly
Resource        resource.robot
Test Setup      Run Keywords  Start Test With Admin Login
...             AND  Go To Register Page
Test Teardown   Run Keywords  Delete Account Test Data
...             AND  Close Browser

*** Test Cases ***
#-- With latest version of wt-forms the required attribute is set on mandatory elements, so form is not submitted
#-- until fields are entered.
# All Fields Unset
#    Register Account
#    Register Page Should Be Open
#    Page Should Contain Element  class:err-msg  limit=4

# Email Is Not An Email
#    Input Contact  not an email
#    Register Account
#    Register Page Should Be Open
#    Page Should Contain  Invalid email address.

Create User
    Fill Register Form  repository
    Register Account
    Page Should Contain  Account created for
    Go To Manage Page
    Page Should Contain  repository_account

Password Does Not Meet Requirements
    Fill Register Form  repository
    Register Account
    Go To Reset Password Page
    Input Password  bad_password
    Input Password Confirmation  bad_password
    Register Account
    Page Should Contain  Password must contain upper & lower case characters, and 1 or more digits & symbols

Password Is Not The Same
    Fill Register Form  repository
    Register Account
    Go To Reset Password Page
    Input Password  GoodPassword123
    Input Password Confirmation  GoodPassword124
    Register Account
    Page Should Contain  The passwords don't match