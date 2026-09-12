"""Bootstrap-owned grants. Future business routes use these permission codes."""

PERMISSIONS = {
    "members.read": "View gym members",
    "members.write": "Create and update gym members",
    "payments.read": "View payments",
    "payments.write": "Record payments",
    "attendance.record": "Record member attendance",
    "users.manage": "Manage staff accounts and access",
    "reports.read": "View business reports",
}

ROLE_PERMISSIONS = {
    "Admin": frozenset(PERMISSIONS),
    "Receptionist": frozenset({
        "members.read", "members.write", "payments.read", "payments.write", "attendance.record",
    }),
    "Trainer": frozenset({"members.read", "attendance.record"}),
    "Owner": frozenset({"members.read", "payments.read", "reports.read"}),
}
