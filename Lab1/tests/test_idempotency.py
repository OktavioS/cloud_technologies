import time
import uuid


def notes_count(client, user_id):
    response = client.get(f"/users/{user_id}")
    response.raise_for_status()
    return response.json()["notes_count"]


def test_same_key_creates_one_note_and_same_response(client, user):
    key = str(uuid.uuid4())
    headers = {**user["headers"], "Idempotency-Key": key}
    payload = {"title": "idempotent note", "body": "created once"}

    first = client.post("/notes", json=payload, headers=headers)
    second = client.post("/notes", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert notes_count(client, user["id"]) == 1


def test_without_key_creates_two_notes(client, user):
    payload = {"title": "plain note", "body": ""}

    first = client.post("/notes", json=payload, headers=user["headers"])
    second = client.post("/notes", json=payload, headers=user["headers"])

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert notes_count(client, user["id"]) == 2


def test_same_key_with_different_body_is_rejected(client, user):
    headers = {**user["headers"], "Idempotency-Key": str(uuid.uuid4())}

    first = client.post("/notes", json={"title": "first"}, headers=headers)
    second = client.post("/notes", json={"title": "second"}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 422
    assert notes_count(client, user["id"]) == 1


def test_async_same_key_returns_same_job_and_one_note(client, user):
    headers = {**user["headers"], "Idempotency-Key": str(uuid.uuid4())}
    payload = {"title": "async note", "body": "via queue"}

    first = client.post("/notes/async", json=payload, headers=headers)
    second = client.post("/notes/async", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json() == second.json()

    job_url = first.json()["status_url"]
    deadline = time.time() + 60
    job = {}
    while time.time() < deadline:
        job = client.get(job_url, headers=user["headers"]).json()
        if job.get("status") == "done":
            break
        time.sleep(1)

    assert job.get("status") == "done"
    assert notes_count(client, user["id"]) == 1
