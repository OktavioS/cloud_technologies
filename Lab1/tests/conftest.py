import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30) as http:
        yield http


@pytest.fixture
def user(client):
    username = f"test_{uuid.uuid4().hex[:12]}"
    password = "test-password-123"
    client.post("/auth/register", json={"username": username, "password": password}).raise_for_status()
    login = client.post("/auth/login", json={"username": username, "password": password})
    login.raise_for_status()
    data = login.json()
    return {"id": data["user_id"], "headers": {"Authorization": f"Bearer {data['access_token']}"}}
