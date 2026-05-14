*** Settings ***
Documentation   JPER test suites
Library         SeleniumLibrary
Library         tests.fixtures.robot
Suite Setup     Run Keywords  robot.server_setup
Suite Teardown  Run Keywords  robot.server_teardown
# Test Teardown   Run Keywords  Delete Account Test Data AND Reset Harvester Data AND Delete Identifier Test Data
# ...             AND Close Browser
