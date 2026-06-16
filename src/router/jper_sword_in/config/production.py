"""
Production environment specific configuration for Router SWORD-IN

On deployment, configuration can be overridden by using a local ~/.pubrouter/sword-in.cfg file
"""
# Whether SWORD model code should delete SWORD2 deposit after successfully converting it into Router Notification
# If False, then deposit will remain in TempStore until a separate Scheduler nightly process deletes it after X days
# If True, then the Sword deposit is deleted from TempStore immediately after successfully converting to Notification
DELETE_AFTER_INGEST = False
