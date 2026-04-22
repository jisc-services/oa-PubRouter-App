# -*- coding: robot -*-

*** Settings ***
Documentation   Testing setting of tracking cookie
Resource        resource.robot
Test Teardown   Run Keywords  Close Browser

*** Test Cases ***

Do not set tracking cookie
    # go to login page, the tracking cookie header will be displayed
    Open Browser To Login Page
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}
    # navigate to the cookie page, header should again be visible
    Go To  ${COOKIE PAGE}
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}

Disable tracking
    # go to login page, the tracking cookie header will be displayed
    Open Browser To Login Page
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # Click "No thanks" button
    Click Button  ${COOKIE_BANNER_BTN_LOCATOR} [@value='no']

    # Go to the about/cookies page, the cookie banner should NOT be shown
    Go To  ${COOKIE PAGE}
    Element Should Not Be Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # On the Cookies page, the toggle button should shown Cookies disabled
    Element Should Be Visible  ${COOKIE_TOGGLE_LOCATOR} [@class='cookie-off']

Enable tracking
    # go to login page, the tracking cookie header will be displayed
    Open Browser To Login Page
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # Click "That's fine" button
    Click Button  ${COOKIE_BANNER_BTN_LOCATOR} [@value='yes']

    # Go to the about/cookies page, the cookie banner should NOT be shown
    Go To  ${COOKIE PAGE}
    Element Should Not Be Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # On the Cookies page, the toggle button should shown Cookies enabled
    Element Should Be Visible  ${COOKIE_TOGGLE_LOCATOR} [@class='cookie-on']


Cookie page enable tracking
    # go to login page, the tracking cookie header will be displayed
    Open Browser To Login Page
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # Go to the about/cookies page, the cookie banner should be shown
    Go To  ${COOKIE PAGE}
    Wait Until Element Is Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # The cookie toggle button should be unset (greyed out)
    Element Should Be Visible  ${COOKIE_TOGGLE_LOCATOR} [@class='cookie-unset']

    # Click "No Thanks" button
    Click Button  ${COOKIE_BANNER_BTN_LOCATOR} [@value='no']
    # Buttons should be hidden
    Wait Until Element Is Not Visible  ${COOKIE_BANNER_BTN_LOCATOR}

    # The cookie toggle button should be set to Off
    Element Should Be Visible  ${COOKIE_TOGGLE_LOCATOR} [@class='cookie-off']

    # Now attempt to turn cookies On, by clicking on the toggle button
    Click element  ${COOKIE_TOGGLE_LOCATOR}

    # The cookie toggle button should be set to On
    Element Should Be Visible  ${COOKIE_TOGGLE_LOCATOR} [@class='cookie-on']

