"""Regression tests for phase-aware text parsing and comparison safety across inputs."""

import io
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
    email = f"text_phase_{uuid.uuid4().hex[:10]}@example.com"
    payload = {
        "full_name": "TEST Text Phase",
        "email": email,
        "password": "testpass123",
    }
    response = api_client.post(_api_url("/auth/register"), json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == email
    assert isinstance(data["token"], str) and data["token"]
    return data["token"]


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# Text input parser + phase-aware comparison behavior
def test_text_before_heading_is_before_only_and_no_after_assumption(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text before-only",
        "text": "Before Awareness:\nPatna : environment 15\nSiwan : environment 20",
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "before-only"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["before_total"] == 35
    assert data["summary"]["after_total"] == 0
    assert data["summary"]["awareness_change_percent"] is None


def test_text_after_heading_is_after_only_and_no_before_assumption(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text after-only",
        "text": "After Awareness:\nPatna : health 7\nGaya : health 5",
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "after-only"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["before_total"] == 0
    assert data["summary"]["after_total"] == 12
    assert data["summary"]["awareness_change_percent"] is None


def test_text_both_phases_matching_area_issue_enables_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text both matching",
        "text": "Before Awareness:\nPatna : environment 15\nSiwan : environment 20\n\nAfter Awareness:\nPatna : environment 9\nSiwan : environment 12",
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "both"
    assert data["chart_data"]["focus_mode"] == "single-issue-multi-area"
    assert data["chart_data"]["has_awareness_data"] is True
    assert data["chart_data"]["line_mode"] == "awareness"
    assert "Before vs After" in data["chart_data"]["bar_title"]
    assert all("before" in item and "after" in item for item in data["chart_data"]["bar_data"])
    assert data["summary"]["before_total"] == 35
    assert data["summary"]["after_total"] == 21


def test_text_both_phases_without_matching_pairs_has_no_forced_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text both no matching area pair",
        "text": "Before Awareness:\nPatna : environment 15\n\nAfter Awareness:\nGaya : environment 9",
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "both"
    assert data["chart_data"]["focus_mode"] == "single-issue-multi-area"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["awareness_change_percent"] is None
    assert "exact matching area/issue pairs were not found" in data["insight"]


def test_text_both_phases_same_areas_but_different_issues_still_no_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text same areas but issue mismatch",
        "text": (
            "Before Awareness:\n"
            "Patna : environment 10\n"
            "Siwan : water 8\n\n"
            "After Awareness:\n"
            "Patna : health 6\n"
            "Siwan : crime 4"
        ),
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "both"
    assert data["chart_data"]["focus_mode"] == "mixed"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["awareness_change_percent"] is None
    assert "exact matching area/issue pairs were not found" in data["insight"]


def test_text_one_issue_many_areas_stays_area_wise(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST text one issue many areas",
        "text": "Before Awareness:\nPatna : women safety 12\nSiwan : women safety 8\nGaya : women safety 4",
    }

    response = api_client.post(_api_url("/analysis/text"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["focus_mode"] == "single-issue-multi-area"
    assert "Distribution by Area" in data["chart_data"]["pie_title"]
    assert len(data["chart_data"]["table_rows"]) == 3
    assert {row["area"] for row in data["chart_data"]["table_rows"]} == {"Patna", "Siwan", "Gaya"}


# Manual + file consistency with the same phase-aware comparison rules
def test_manual_both_phases_without_matching_pairs_has_no_comparison(api_client):
    token = _register_and_get_token(api_client)
    payload = {
        "title": "TEST manual no matching pair",
        "rows": [
            {"area": "Patna", "issue": "Environment", "phase": "Before Awareness", "count": 11},
            {"area": "Gaya", "issue": "Environment", "phase": "After Awareness", "count": 6},
        ],
    }

    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()

    assert data["chart_data"]["phase_scope"] == "both"
    assert data["chart_data"]["has_awareness_data"] is False
    assert data["chart_data"]["line_mode"] == "single"
    assert data["summary"]["awareness_change_percent"] is None


def test_file_both_phases_without_matching_pairs_has_no_comparison(api_client):
    token = _register_and_get_token(api_client)

    csv_bytes = b"Area,Issue,Phase,Count\nPatna,Environment,Before Awareness,13\nGaya,Environment,After Awareness,7\n"
    files = {"file": ("phase_no_match.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"title": "TEST file no matching pair"}

    response = api_client.post(
        _api_url("/analysis/file"),
        files=files,
        data=data,
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["chart_data"]["phase_scope"] == "both"
    assert body["chart_data"]["has_awareness_data"] is False
    assert body["chart_data"]["line_mode"] == "single"
    assert body["summary"]["awareness_change_percent"] is None
