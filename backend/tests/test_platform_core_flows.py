"""Core API regression tests for auth, analysis context, file rules, admin access, and isolation."""

import io
import os
import time
import uuid

import pandas as pd
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


def _register_and_login(api_client, email_prefix: str = "testuser"):
    unique = f"{email_prefix}_{uuid.uuid4().hex[:10]}@example.com"
    password = "testpass123"

    register_payload = {
        "full_name": "TEST User",
        "email": unique,
        "password": password,
    }
    register_response = api_client.post(_api_url("/auth/register"), json=register_payload)
    assert register_response.status_code == 200
    register_data = register_response.json()
    assert register_data["user"]["email"] == unique
    assert isinstance(register_data["token"], str) and register_data["token"]

    login_response = api_client.post(
        _api_url("/auth/login"),
        json={"email": unique, "password": password},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["user"]["email"] == unique
    assert isinstance(login_data["token"], str) and login_data["token"]
    return unique, login_data["token"]


def _auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# Auth and profile flow coverage
def test_user_register_login_and_me(api_client):
    email, token = _register_and_login(api_client, "authflow")
    me_response = api_client.get(_api_url("/auth/me"), headers=_auth_headers(token))
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == email
    assert isinstance(me_data["id"], str)


# Manual analysis: single issue across multiple areas
def test_manual_analysis_single_issue_multi_area_focus(api_client):
    _, token = _register_and_login(api_client, "singleissue")
    payload = {
        "title": "TEST Single Issue Multi Area",
        "rows": [
            {"area": "Patna", "issue": "Women Safety", "phase": "Before Awareness", "count": 15},
            {"area": "Siwan", "issue": "Women Safety", "phase": "Before Awareness", "count": 7},
            {"area": "Gaya", "issue": "Women Safety", "phase": "After Awareness", "count": 5},
        ],
    }
    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert data["chart_data"]["focus_mode"] == "single-issue-multi-area"
    assert "Distribution by Area" in data["chart_data"]["pie_title"]
    assert "Distribution by Area" in data["chart_data"]["bar_title"]
    assert "Women Safety" in data["insight"]


# Manual analysis: single area across multiple issues
def test_manual_analysis_single_area_multi_issue_focus(api_client):
    _, token = _register_and_login(api_client, "singlearea")
    payload = {
        "title": "TEST Single Area Multi Issue",
        "rows": [
            {"area": "Patna", "issue": "Women Safety", "phase": "Before Awareness", "count": 14},
            {"area": "Patna", "issue": "Health", "phase": "After Awareness", "count": 6},
            {"area": "Patna", "issue": "Water", "phase": "Before Awareness", "count": 10},
        ],
    }
    response = api_client.post(_api_url("/analysis/manual"), json=payload, headers=_auth_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert data["chart_data"]["focus_mode"] == "single-area-multi-issue"
    assert "Issue Breakdown" in data["chart_data"]["pie_title"]
    assert "Issue Comparison" in data["chart_data"]["bar_title"]
    assert "Patna" in data["insight"]


# File upload format guardrails and parsing
def test_file_upload_accepts_csv_and_rejects_pdf(api_client):
    _, token = _register_and_login(api_client, "fileflow")

    csv_bytes = b"Area,Issue,Count\nPatna,Women Safety,11\nSiwan,Health,4\n"
    files = {"file": ("test_data.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"title": "TEST CSV Upload"}
    csv_response = api_client.post(
        _api_url("/analysis/file"),
        files=files,
        data=data,
        headers=_auth_headers(token),
    )
    assert csv_response.status_code == 200
    csv_json = csv_response.json()
    assert csv_json["source_type"] == "file"
    assert csv_json["file_metadata"]["filename"] == "test_data.csv"

    xlsx_df = pd.DataFrame(
        [
            {"Area": "Gaya", "Issue": "Water", "Count": 8},
            {"Area": "Patna", "Issue": "Health", "Count": 3},
        ]
    )
    xlsx_buffer = io.BytesIO()
    xlsx_df.to_excel(xlsx_buffer, index=False)
    xlsx_buffer.seek(0)
    xlsx_files = {
        "file": (
            "test_data.xlsx",
            xlsx_buffer,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    xlsx_response = api_client.post(
        _api_url("/analysis/file"),
        files=xlsx_files,
        data={"title": "TEST XLSX Upload"},
        headers=_auth_headers(token),
    )
    assert xlsx_response.status_code == 200
    xlsx_json = xlsx_response.json()
    assert xlsx_json["file_metadata"]["filename"] == "test_data.xlsx"

    pdf_files = {"file": ("test_data.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    pdf_response = api_client.post(
        _api_url("/analysis/file"),
        files=pdf_files,
        data={"title": "TEST PDF Upload"},
        headers=_auth_headers(token),
    )
    assert pdf_response.status_code == 400
    assert "CSV or XLSX" in pdf_response.json()["detail"]


# Default admin auth and global endpoint access
def test_admin_default_login_and_dashboard_access(api_client):
    response = api_client.post(
        _api_url("/admin/login"),
        json={"username": "IITPATNACAPSTONE", "password": "computerscience"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "IITPATNACAPSTONE"
    assert isinstance(data["token"], str) and data["token"]

    submissions_response = api_client.get(
        _api_url("/admin/submissions"),
        headers=_auth_headers(data["token"]),
    )
    assert submissions_response.status_code == 200
    assert isinstance(submissions_response.json(), list)


# Per-user data isolation for analysis history
def test_analysis_history_isolation_between_users(api_client):
    _, token_user_one = _register_and_login(api_client, "historya")
    _, token_user_two = _register_and_login(api_client, "historyb")

    payload_user_one = {
        "title": f"TEST UserOne Analysis {time.time()}",
        "rows": [
            {"area": "Patna", "issue": "Environment", "phase": "Before Awareness", "count": 9},
            {"area": "Siwan", "issue": "Environment", "phase": "After Awareness", "count": 4},
        ],
    }
    create_response = api_client.post(
        _api_url("/analysis/manual"),
        json=payload_user_one,
        headers=_auth_headers(token_user_one),
    )
    assert create_response.status_code == 200
    created_analysis_id = create_response.json()["id"]

    history_one = api_client.get(_api_url("/analysis/history"), headers=_auth_headers(token_user_one))
    assert history_one.status_code == 200
    user_one_ids = {item["id"] for item in history_one.json()}
    assert created_analysis_id in user_one_ids

    history_two = api_client.get(_api_url("/analysis/history"), headers=_auth_headers(token_user_two))
    assert history_two.status_code == 200
    user_two_ids = {item["id"] for item in history_two.json()}
    assert created_analysis_id not in user_two_ids

    detail_for_user_two = api_client.get(
        _api_url(f"/analysis/history/{created_analysis_id}"),
        headers=_auth_headers(token_user_two),
    )
    assert detail_for_user_two.status_code == 404
