# -*- coding: robot -*-
*** Settings ***
Documentation           A resource file which contains keywords that can be used
...                     across the other tests.
# import selenium library with timeout of 10 secs and with implicit wait value of 2 seconds (how long it'll wait
# when trying to find an element before quitting)
Library                 SeleniumLibrary
# See file tests/fixtures/robot.py
Library                 tests.fixtures.robot

*** Variables ***
${URL_SCHEME}           http  # https
${SERVER}               localhost:5000  # XXX.YYYY.ac.uk/robot
${SERVER_WITH_SCHEME}   ${URL_SCHEME}://${SERVER}
${BROWSER}              Chrome
${DELAY}                0
${ADMIN USER}           admin
${ADMIN PASSWORD}       admin
${HOME PAGE}            ${SERVER_WITH_SCHEME}/
${LOGIN PAGE}           ${SERVER_WITH_SCHEME}/account/login
${ADMIN PAGE}           ${SERVER_WITH_SCHEME}/account/${ADMIN_USER}
${REGISTER PAGE}        ${SERVER_WITH_SCHEME}/account/register
${MANAGE PAGE}          ${SERVER_WITH_SCHEME}/account/
${ADMIN PANEL PAGE}     ${SERVER_WITH_SCHEME}/admin/
${REPORTS PAGE}         ${SERVER_WITH_SCHEME}/reports/
${WEBSERVICES LIST PAGE}      ${SERVER_WITH_SCHEME}/harvester/webservice/
${WEBSERVICE MANAGE PAGE}  ${SERVER_WITH_SCHEME}/harvester/manage/
${COOKIE PAGE}           ${SERVER_WITH_SCHEME}/website/cookies/
${CSV_FILE}             match_params.csv
${DUPLICATE_CSV_FILE}   duplicate_match_params.csv
${BAD_FILE}             bad_file.txt
${INVALID_FILE}         invalid_params.csv
${IDS_FILE}             identifiers.csv
${USER}                 myuser@myuser.user
${USER PASSWORD}        a_STRONG_password_123

${COOKIE_BANNER_BTN_LOCATOR}    xpath:/html/body/div[@id='cookie-container']/div/div[@class='col span-4']/button
${COOKIE_TOGGLE_LOCATOR}        xpath://button[@id='cookie-toggle-button']


# --- Utilities ---
Page Should Contain Element With Value
    [Arguments]  ${text}
    Page Should Contain Element  //*[contains(@value, '${text}')]

Page Should Not Contain Element With Value
    [Arguments]  ${text}
    Page Should Not Contain Element  //*[contains(@value, '${text}')]

Page Should Contain Element With Class
    [Arguments]  ${class}
    Page Should Contain Element  css:.${class}

Page Should Not Contain Element With Class
    [Arguments]  ${class}
    Page Should Not Contain Element  css:.${class}

Wait Until Element With Class Is Visible
    [Arguments]  ${class}
    Wait Until Element Is Visible  css:.${class}

Click Element By Text
    [Arguments]  ${text}
    Click Element  //*[contains(text(), '${text}')]

Click Element By Exact Text
    [Arguments]  ${text}
    Click Element  //*[. = '${text}']

Get File From Resources And Upload
    [Arguments]  ${locator}  ${filename}
    ${path} =  Join Paths Together  ${CURDIR}  resources  ${filename}
    Choose File  ${locator}  ${path}

# --- Page movement ---
Open Browser To Login Page
    Open Browser  ${LOGIN PAGE}  ${BROWSER}
    Set Selenium Speed  ${DELAY}
    Login Page Should Be Open

Go To My Account Page
    Click Element By Text  My Account

Go To Account Config Page
    ${url} =  Get Element Attribute  //*[contains(text(), 'Set or view matching parameters')]  href
    Go To  ${url}
    Location Should Contain  configview

Go To Login Page
    Go To  ${LOGIN PAGE}

Go To Register Page
    Go To  ${REGISTER PAGE}

Go To Manage Page
    [Arguments]  ${endpoint}=
    Go To  ${MANAGE PAGE}${endpoint}

Go To Admin Panel Page
    Go To  ${ADMIN PANEL PAGE}

Go To Reports Page
    Go To  ${REPORTS PAGE}

Go To Webservice Page
    Go To  ${WEBSERVICES LIST PAGE}

Go To Add Webservice Page
    Go To  ${WEBSERVICE MANAGE PAGE}

Go To Reset Password Page
    Wait Until Page Contains  Password Reset Link
    Click Element By Exact Text  Password Reset Link

Home Page Should Be Open
    Location Should Be  ${HOME PAGE}

Login Page Should Be Open
    Location Should Be  ${LOGIN PAGE}

Register Page Should Be Open
    Location Should Be  ${REGISTER PAGE}

Admin Account Page Should Be Open
    Location Should Be  ${ADMIN PAGE}

Webservices-list-page-shown
    Location Should Contain  ${WEBSERVICES LIST PAGE}

Webservice-manage-page-shown
    Location Should Contain  ${WEBSERVICE MANAGE PAGE}

Decline Cookies
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}
    # Click "No thanks" on cookie tracking banner
    Click Button  ${COOKIE_BANNER_BTN_LOCATOR} [@value='no']
    Wait Until Element Is Not Visible  ${COOKIE_BANNER_BTN_LOCATOR}

# --- Login ---
Input Username
    [Arguments]  ${username}
    Input Text  username  ${username}

Input Password
    [Arguments]  ${password}
    Input Text  password  ${password}

Submit Credentials
    Click Element  id:login

Logout Current User
    Run Keyword And Ignore Error  Click Element By Text  Log out

Login User
    [Arguments]  ${username}  ${password}
    Logout Current User
    Go To  ${LOGIN PAGE}
    Input Username  ${username}
    Input Password  ${password}
    Submit Credentials

Start Test With Admin Login
    Open Browser To Login Page
    Decline Cookies
    Admin Login

Admin Login
    Login User  ${ADMIN USER}  ${ADMIN PASSWORD}
    Admin Account Page Should Be Open

# --- Account Registration ---
Input Org Name
    [Arguments]  ${org name}
    Input Text  organisation_name  ${org_name}

Input Create Username
    [Arguments]  ${username}
    Input Text  username  ${username}

Input Contact
    [Arguments]  ${email}
    Input Text  contact_email  ${email}

Input Password Confirmation
    [Arguments]  ${password}
    Input Text  password_verify  ${password}

Input Password And Confirm
    [Arguments]  ${password}
    Input Password  ${password}
    Input Password Confirmation  ${password}

Input Note
    [Arguments]  ${note}
    Input Text  note  ${note}

Set Account Type
    [Arguments]  ${type}
    Select Radio Button  role  ${type}

Register Account
    Click Element  id:register

Fill Register Form
    [Arguments]  ${type}  ${email}=${USER}
    Input Create Username  ${type}_account
    Input Org Name  ${type}_account
    Input Contact  ${email}
    Input Note  My Note
    Set Account Type  ${type}

# --- Generic forms ---
Update User Details
    [Arguments]  ${org name}  ${note}  ${contact_email}
    Input Org Name  ${org name}
    Input Note  ${note}
    Input Text  contact_email  ${contact_email}
    Click Element  id:update_general


# Badly named on form, should be Org Name
Account Org Name Should Be
    [Arguments]  ${org_name}
    Textfield Value Should Be  organisation_name  ${org_name}

Note Should Be
    [Arguments]  ${note}
    Textarea Value Should Be  note  ${note}

Username Should Be
    [Arguments]  ${username}
    Textfield Value Should Be  username  ${username}

Contact Email Should Be
    [Arguments]  ${contact_email}
    Textfield Value Should Be  contact_email  ${contact_email}

# --- Repository forms ---
Set Max Pub Age
    [Arguments]  ${age}
    Input Text  pub_years  ${age}
    Click Element  id:max_age

Upload Matching Params
    [Arguments]  ${file}
    Click Element By Text  Set parameters
    Get File From Resources And Upload  file  ${file}
    Wait Until Element Is Visible  config_upload
    Click Element  id:config_upload

Upload Bad Matching Params
    Upload Matching Params  ${BAD_FILE}

Upload Invalid Matching Params
    Upload Matching Params  ${INVALID_FILE}

Upload Good Matching Params
    Upload Matching Params  ${CSV_FILE}

Upload Good Duplicate Matching Params
    Upload Matching Params  ${DUPLICATE_CSV_FILE}

Select Repository XML Format
    [Arguments]  ${format}
    Select From List By Value  id:xml_format  ${format}

Pub Age Should Be
    [Arguments]  ${age}
    Textfield Value Should Be  pub_years  ${age}

Go Live On Repository
    Click Element By Text  How to move from Test to Live
    Wait Until Element Is Visible  golive
    Click Element  id:golive
    Handle Alert

# --- Publisher Forms ---
Set Embargo Duration
    [Arguments]  ${duration}
    Input Text  embargo_duration  ${duration}

Embargo Should Be
    [Arguments]  ${duration}
    Textfield Value Should Be  embargo_duration  ${duration}

Set Licence URL
    [Arguments]  ${lic}
    Input Text  license_url  ${lic}

Licence URL Should Be
    [Arguments]  ${lic}
    Textfield Value Should Be  license_url  ${lic}

Update Embargo License
    Click Element  id:update_lic

Go To Deposit History Page
    ${url} =  Get Element Attribute  //*[contains(text(), 'View deposit history')]  href
    Go To  ${url}
    Location Should Contain  deposit_history

Show History From
    [Arguments]  ${from}  ${to}
    Input Text  from_date  ${from}
    Input Text  to_date  ${to}
    Click Element By Exact Text  Show history

# --- User creation and login ---
Reset Password
    [Arguments]  ${email}
    Go To Reset Password Page
    Input Password And Confirm  ${USER_PASSWORD}
    Register Account

Create Test User
    [Arguments]  ${repository}  ${email}
    Go To Register Page
    Fill Register Form  ${repository}  ${email}
    Register Account
    Reset Password  ${email}

Create Test Repository
    Create Test User  repository  repo_email@email.com

Create Test Publisher
    Create Test User  publisher  publisher_email@email.com

Login Repository User
    Login User  repo_email@email.com  ${USER_PASSWORD}

Open Login Repository
    Open Browser To Login Page
    Decline Cookies
    Login Repository User

Login Repository User Click Sword
    Open Login Repository
    Go To My Account Page
    Click Element By Text  Receive notifications directly
    Wait Until Element Is Visible  id:repository_name

Login Publisher User
    Login User  publisher_email@email.com  ${USER_PASSWORD}

Manage User
    [Arguments]  ${endpoint}
    Go To Manage Page  ${endpoint}
    Wait Until Element Is Visible  //td[. = 'Manage']/a
    Click Element  //td[. = 'Manage']/a
    Page Should Contain  Admin only account management

Manage Repository User
    Manage User  test-repositories

Manage Publisher User
    Manage User  publishers

Create And Login Repository User
    Create Test Repository
    Login Repository User
    Go To My Account Page
    Click Element By Text  Receive notifications directly
    Wait Until Element Is Visible  id:repository_name

Create And Login Publisher User
    Create Test Publisher
    Login Publisher User
    Go To My Account Page

Create And Manage Repository User
    Create Test Repository
    Manage Repository User

Create And Manage Publisher User
    Create Test Publisher
    Manage Publisher User

# --- Identifiers ---
Focus Fuzzy Search And Enter Text
    [Arguments]  ${id}  ${text}
    Set Focus To Element  ${id}
    Press Keys  ${id}  ${text}

Clear Jisc Identifiers
    Clear Element Text  jisc_id

Focus Jisc Identifiers And Enter Text
    [Arguments]  ${text}
    Focus Fuzzy Search And Enter Text  jisc_id  ${text}

Wait For Jisc Identifier Search Box
    Wait Until Element Is Visible  ui-id-1

Enter Text For Jisc Identifiers And Select Option
    [Arguments]  ${text}
    Focus Jisc Identifiers And Enter Text  ${text}
    Wait For Jisc Identifier Search Box
    Click Element  //div[@class='ui-menu-item-wrapper']

Jisc Identifier Name Should Be
    [Arguments]  ${name}
    Textfield Value Should Be  jisc_id_name  ${name}

Load Identifiers
    Get File From Resources And Upload  csv_file  ${IDS_FILE}
    Click Element By Exact Text  Load identifiers

# --- Harvester Webservices ---
Select Harvester Webservice Row And Click Element
    [Arguments]  ${name}  ${action}
    # This is a quite complicated XPATH expression, as it didn't seem possible to grab the <a>
    # element by it's text (respectively edit or delete)
    Click Element  //tr[td/text() = '${name}']/td[last()]//a[@class='button']

Edit Harvester Webservice
    [Arguments]  ${name}
    Select Harvester Webservice Row And Click Element  ${name}  edit

Input Endpoint URL
    ${url} =  Default EPMC Url
    Input Text  url  ${url}

Input Webservice Name
    [Arguments]  ${name}
    Input Text  name  ${name}

Input Default Query
    Input Text  query  {"query": {"match_all": {}}}

Input Start Date
    [Arguments]  ${date}
    # Badly named field
    Input Text  end_date  ${date}

Input Wait Window
    [Arguments]  ${wait}
    Input Text  wait_window  ${wait}

Submit Webservice
    Click Element  id:save

Fill Webservice Form
    Go To Add Webservice Page
    Input Endpoint URL
    Input Webservice Name  Other EPMC
    Input Default Query
    Input Start Date  2017-08-01
    Input Wait Window  30

Fill Webservice Form And Submit
    Fill Webservice Form
    Submit Webservice

Uncheck And Save All Sources
    Click Element  xpath://table[@id="harv-note-srcs"]//button[@value="off"]
    All Checkboxes Should Be Unticked
    Click Element  id:save_srcs

Check And Save All Sources
    Click Element  xpath://table[@id="harv-note-srcs"]//button[@value="on"]
    All Checkboxes Should Be Ticked
    Click Element  id:save_srcs

All Checkboxes Should Be Ticked
    Page Should Not Contain Element  css: input[type="checkbox"]:not(:checked)

All Checkboxes Should Be Unticked
    Page Should Not Contain Element  css: input:checked[type='checkbox']


