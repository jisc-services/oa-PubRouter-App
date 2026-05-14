#!/usr/bin/env python
"""
Script to create an Organisation Admin account with it's default User accounts user for NEW Publications Router installation.

Usage:
    create_admin_user

"""
import uuid
from octopus.core import initialise
from router.shared.create_admin_acc import create_admin_user
from router.jper.app import app

with app.app_context():
    initialise()
    api_key = str(uuid.uuid4())
    ac_created, acc = create_admin_user(api_key)
    print("\n=== {} ===\n=== {}. ===\n".format(
        f"New Admin account CREATED with api_key: {api_key}" if ac_created else "Admin account already exists",
        f"User account ID: {acc.id}, User UUID: {acc.uuid}; Admin Org account ID: {acc.acc_org.id}, Org UUID: {acc.acc_org.uuid}")
    )