# JPER Sword-In Config

This directory contains the base configuration [base.py](base.py) and environment specific configuration files for Development, Test, Staging and Production environments.

IMPORTANT: Note that certain values defined within the Sword-In configuration OVERRIDE values of the same name that are defined in JPER config (src/router/jper/config/base.py) which is loaded by Sword-In app creation BEFORE the Sword-In config (which is loaded last).

