"""
get_db, get_current_user (Bearer token -> CurrentUser, role re-read from DB), require_employee, require_manager.
403 for a wrong role; 404 for records that belong to someone else.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""
