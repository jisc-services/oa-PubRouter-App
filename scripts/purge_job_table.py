#!/usr/bin/env python

"""
Script to PURGE the `job` table.

Rationale: Resets record auto-increment ID to 1.

Impact: Any running services that use `schedule.py` will terminate.
"""
from router.shared.models.schedule import Job
from router.jper.app import app

with app.app_context():
    try:
        Job.purge_all_jobs()
        print("\n\n*** Job table has been PURGED ***\n\n")
        exit(0)
    except Exception as e:
        print(f"\n\n!!! Purge failed with error - repr(e) !!!\n\n")
        exit(1)
