"""Bootstrap-owned grants. Future business routes use these permission codes."""

PERMISSIONS = {
    "dashboard.read": "View the operational dashboard",
    "members.read": "View gym members",
    "members.write": "Create and update gym members",
    "members.deactivate": "Deactivate and reactivate gym members",
    "memberships.read": "View membership plans and subscriptions",
    "memberships.write": "Manage membership plans and subscriptions",
    "subscriptions.read": "View subscriptions",
    "subscriptions.write": "Create and renew subscriptions",
    "payments.read": "View payments",
    "payments.write": "Record payments",
    "attendance.read": "View attendance",
    "attendance.record": "Record member attendance",
    "trainers.read": "View trainers and assignments",
    "trainers.write": "Manage trainers and assignments",
    "workouts.read": "View workout plans and exercises",
    "workouts.write": "Manage workout plans and exercises",
    "users.manage": "Manage staff accounts and access",
    "reports.read": "View business reports",
    "settings.manage": "Manage application settings",
}

ROLE_PERMISSIONS = {
    "Admin": frozenset(PERMISSIONS),
    "Receptionist": frozenset(
        {
            "dashboard.read",
            "members.read",
            "members.write",
            "members.deactivate",
            "memberships.read",
            "memberships.write",
            "subscriptions.read",
            "subscriptions.write",
            "payments.read",
            "payments.write",
            "attendance.read",
            "attendance.record",
            "trainers.read",
            "workouts.read",
        }
    ),
    "Trainer": frozenset(
        {
            "dashboard.read",
            "members.read",
            "attendance.read",
            "attendance.record",
            "trainers.read",
            "workouts.read",
            "workouts.write",
        }
    ),
    "Owner": frozenset(
        {
            "dashboard.read",
            "members.read",
            "memberships.read",
            "subscriptions.read",
            "payments.read",
            "attendance.read",
            "trainers.read",
            "workouts.read",
            "reports.read",
        }
    ),
}
