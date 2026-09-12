from datetime import date


def csrf(client):
    return {"X-CSRF-Token": client.get("/auth/csrf").json()["csrf_token"]}


def test_member_api_crud_search_pagination_and_permissions(client, login):
    assert login("receptionist").status_code == 200
    response = client.post(
        "/api/members", json={"full_name": "Hazem Salah", "phone": "01012345678"}, headers=csrf(client)
    )
    assert response.status_code == 201
    member_id = response.json()["id"]
    found = client.get("/api/members", params={"search": "Hazem", "page": 1}).json()
    assert found["total"] == 1 and found["items"][0]["member_number"].startswith("GYM-")
    response = client.put(
        f"/api/members/{member_id}", json={"full_name": "Hazem Updated", "phone": "01012345678"}, headers=csrf(client)
    )
    assert response.status_code == 200 and response.json()["full_name"] == "Hazem Updated"
    assert (
        client.post(f"/api/members/{member_id}/status", params={"active": False}, headers=csrf(client)).status_code
        == 200
    )
    client.post("/auth/logout", headers=csrf(client))
    assert login("trainer").status_code == 200
    assert (
        client.post(
            "/api/members", json={"full_name": "Blocked", "phone": "01011111111"}, headers=csrf(client)
        ).status_code
        == 403
    )


def test_financial_and_attendance_api_flow(client, login):
    login("admin")
    member = client.post(
        "/api/members", json={"full_name": "Member One", "phone": "01012345678"}, headers=csrf(client)
    ).json()
    plan = client.post(
        "/api/membership-plans", json={"name": "Monthly", "duration_months": 1, "price": "500"}, headers=csrf(client)
    ).json()
    sub = client.post(
        "/api/subscriptions",
        json={
            "member_id": member["id"],
            "plan_id": plan["id"],
            "requested_start_date": str(date.today()),
            "discount_amount": "50",
        },
        headers=csrf(client),
    )
    assert sub.status_code == 201 and sub.json()["final_price"] == 450.0
    payment = client.post(
        "/api/payments",
        json={"member_id": member["id"], "subscription_id": sub.json()["id"], "amount": "100", "method": "cash"},
        headers=csrf(client),
    )
    assert payment.status_code == 201 and payment.json()["remaining_balance"] == 350.0
    assert (
        client.post(
            "/api/payments",
            json={"member_id": member["id"], "subscription_id": sub.json()["id"], "amount": "351", "method": "cash"},
            headers=csrf(client),
        ).status_code
        == 409
    )
    assert client.post("/api/attendance", json={"member_id": member["id"]}, headers=csrf(client)).status_code == 201
    assert client.post("/api/attendance", json={"member_id": member["id"]}, headers=csrf(client)).status_code == 409


def test_web_pages_render_and_report_csv_is_authorized(client, login):
    assert client.get("/dashboard", follow_redirects=False).status_code == 401
    login("admin")
    for path in (
        "/dashboard",
        "/members",
        "/memberships",
        "/payments",
        "/attendance",
        "/trainers",
        "/workouts",
        "/reports",
        "/users",
        "/settings",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Gym Management" in response.text
        assert response.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    report = client.get("/reports/active-members.csv")
    assert report.status_code == 200 and "text/csv" in report.headers["content-type"]


def test_trainer_workout_and_staff_admin_api(client, login, credential):
    login("admin")
    member = client.post(
        "/api/members", json={"full_name": "Workout Member", "phone": "01012345678"}, headers=csrf(client)
    ).json()
    trainer = client.post(
        "/api/trainers", json={"full_name": "Coach One", "phone": "01022223333"}, headers=csrf(client)
    ).json()
    assignment = client.post(
        "/api/trainer-assignments",
        json={"trainer_id": trainer["id"], "member_id": member["id"], "start_date": str(date.today())},
        headers=csrf(client),
    )
    assert assignment.status_code == 201 and assignment.json()["is_active"]
    exercise = client.post(
        "/api/exercises", json={"name": "Squat", "muscle_group": "Legs"}, headers=csrf(client)
    ).json()
    workout = client.post(
        "/api/workouts",
        json={
            "name": "Leg day",
            "member_id": member["id"],
            "trainer_id": trainer["id"],
            "start_date": str(date.today()),
        },
        headers=csrf(client),
    ).json()
    item = client.post(
        f"/api/workouts/{workout['id']}/exercises",
        json={"exercise_id": exercise["id"], "position": 1, "sets": 4, "reps": 8},
        headers=csrf(client),
    )
    assert item.status_code == 201
    assert client.get(f"/api/workouts/{workout['id']}").json()["exercises"][0]["name"] == "Squat"
    staff = client.post(
        "/api/users",
        json={
            "username": "desk2",
            "email": "desk2@example.com",
            "password": credential[0],
            "role_name": "Receptionist",
        },
        headers=csrf(client),
    )
    assert staff.status_code == 201 and "password" not in staff.text
    assert (
        client.post(f"/api/users/{staff.json()['id']}/status", params={"active": False}, headers=csrf(client)).json()[
            "is_active"
        ]
        is False
    )


def test_only_admin_can_manage_users(client, login, credential):
    login("receptionist")
    response = client.post(
        "/api/users",
        json={"username": "blocked", "email": "blocked@example.com", "password": credential[0], "role_name": "Trainer"},
        headers=csrf(client),
    )
    assert response.status_code == 403
