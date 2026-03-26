"""Regression tests for phase-aware analysis behavior, file upload rules, and admin default login."""

import os
import uuid

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _api_url(path: str) -> str:
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL is not set")
    return f"{BASE_URL.rstrip('/')}/api{path}"


@pytest.fixture
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


def _register_and_get_token(api_client):
    email = f"phase_req_{uuid.uuid4().hex[:10]}@example.com"
    password = "testpass123"
    payload = {"full_name": "TEST Phase User", "email": email, "password": password}
    register_response = api_client.post(_api_url("/auth/register"), json=payload)
    assert register_response.status_code == 200
    register_data = register_response.json()
    assert register_data["user"]["email"] == email
    assert isinstance(register_data["token"], str) and register_data["token"]
    return register_data["token"]


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# Manual analysis phase-specific behavior coverage
def test_manual_before_only_does_not_trigger_awareness_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST Before Only",
        "rows": [
            {"area": "Patna", "issue": "Women Safety", "phase": "Before Awareness", "count": 12},
            {"area": "Siwan", "issue": "Women Safety", "phase": "Before Awareness", "count": 7},
        ],
    }

    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "before-only"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["awareness_change_percent"] is None
    assert "Before vs After" not in data["chart_data"]["pie_title"]
    assert data["summary"]["before_total"] == 19
    assert data["summary"]["after_total"] == 0


def test_manual_after_only_does_not_trigger_awareness_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST After Only",
        "rows": [
            {"area": "Patna", "issue": "Health", "phase": "After Awareness", "count": 5},
            {"area": "Gaya", "issue": "Health", "phase": "After Awareness", "count": 3},
        ],
    }

    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "after-only"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["awareness_change_percent"] is None
    assert "Before vs After" not in data["chart_data"]["pie_title"]
    assert data["summary"]["before_total"] == 0
    assert data["summary"]["after_total"] == 8


def test_manual_both_phases_explicitly_compares_before_vs_after(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST Before After Compare",
        "rows": [
            {"area": "Patna", "issue": "Education", "phase": "Before Awareness", "count": 20},
            {"area": "Patna", "issue": "Education", "phase": "After Awareness", "count": 10},
            {"area": "Siwan", "issue": "Education", "phase": "Before Awareness", "count": 6},
            {"area": "Siwan", "issue": "Education", "phase": "After Awareness", "count": 4},
        ],
    }

    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "both"
    assert data["chart_data"]["has_awareness_data"] is True
    assert data["chart_data"]["line_mode"] == "awareness"
    assert "Distribution by Area" in data["chart_data"]["pie_title"]
    assert "Before vs After" in data["chart_data"]["bar_title"]
    assert data["summary"]["before_total"] == 26
    assert data["summary"]["after_total"] == 14
    assert isinstance(data["summary"]["awareness_change_percent"], (int, float))
    assert "Before Awareness total is" in data["insight"]
    assert all("before" in item and "after" in item for item in data["chart_data"]["bar_data"])


# Admin default credential validation coverage
def test_admin_default_login_works(api_client):
    response = api_client.post(
        _api_url("/admin/login"),
        json={"username": "IITPATNACAPSTONE", "password": "computerscience"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "IITPATNACAPSTONE"
    assert isinstance(data["token"], str) and data["token"]
