import csv
import io
import logging
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL")

if not mongo_url:
    raise Exception("MONGO_URL not found")

client = AsyncIOMotorClient(mongo_url)

db_name = os.environ.get("DB_NAME", "awareness_db")
db = client[db_name]

JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_EXPIRE_MINUTES = int(os.environ["JWT_EXPIRE_MINUTES"])
JWT_ALGORITHM = "HS256"

DEFAULT_ADMIN_USERNAME = "IITPATNACAPSTONE"
DEFAULT_ADMIN_PASSWORD = "computerscience"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_security = HTTPBearer(auto_error=False)

ISSUE_KEYWORDS = [
    "women safety",
    "environment",
    "health",
    "education",
    "sanitation",
    "water",
    "employment",
    "crime",
    "child welfare",
]

KNOWN_AREAS = [
    "patna",
    "siwan",
    "gaya",
    "muzaffarpur",
    "nalanda",
    "begusarai",
    "bhagalpur",
    "darbhanga",
    "arrah",
    "samastipur",
]

PHASE_MAP = {
    "before": "Before Awareness",
    "before awareness": "Before Awareness",
    "after": "After Awareness",
    "after awareness": "After Awareness",
}

app = FastAPI()
api_router = APIRouter(prefix="/api")


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: Optional[str] = Field(default="", max_length=120)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = ""
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminAuthResponse(BaseModel):
    token: str
    username: str


class AdminPasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)
    new_username: Optional[str] = None


class DataRowInput(BaseModel):
    area: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    phase: Optional[str] = None
    count: int = Field(ge=0)


class ManualAnalyzeRequest(BaseModel):
    rows: List[DataRowInput]
    title: Optional[str] = "Manual Entry Analysis"


class TextAnalyzeRequest(BaseModel):
    text: str = Field(min_length=1)
    title: Optional[str] = "Text Input Analysis"


class AnalysisResult(BaseModel):
    id: str
    user_id: str
    source_type: str
    title: str
    rows: List[DataRowInput]
    summary: Dict[str, Any]
    chart_data: Dict[str, Any]
    insight: str
    file_metadata: Optional[Dict[str, Any]] = None
    raw_input_excerpt: Optional[str] = None
    created_at: str


class CommunitySubmissionCreate(BaseModel):
    area: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    description: str = Field(min_length=4)


class CommunitySubmissionResponse(BaseModel):
    id: str
    user_id: str
    user_email: EmailStr
    area: str
    issue_type: str
    description: str
    created_at: str


class MessageResponse(BaseModel):
    message: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_phrase(value: str) -> str:
    parts = [part for part in str(value).strip().split() if part]
    return " ".join(word.capitalize() for word in parts)


def standardize_phase(phase: Optional[str]) -> Optional[str]:
    if phase is None:
        return None
    key = str(phase).strip().lower()
    return PHASE_MAP.get(key)


def hash_password(password):
    password = password[:72]   # limit fix
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password[:72], hashed_password)


def create_access_token(subject: str, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload: Dict[str, Any] = {"sub": subject, "role": role, "exp": expire_at}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_security),
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization token missing")
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


async def get_current_user(payload: Dict[str, Any] = Depends(get_token_payload)) -> Dict[str, Any]:
    if payload.get("role") != "user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User access required")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_current_admin(payload: Dict[str, Any] = Depends(get_token_payload)) -> Dict[str, Any]:
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    admin_settings = await db.admin_settings.find_one({}, {"_id": 0})
    if not admin_settings:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin settings unavailable")
    return admin_settings


def normalize_rows(rows: List[Dict[str, Any]], strict_count: bool = True) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for raw in rows:
        area = clean_phrase(raw.get("area", ""))
        issue = clean_phrase(raw.get("issue", ""))
        phase = standardize_phase(raw.get("phase"))

        count_raw = raw.get("count")
        if (
            count_raw is None
            or (isinstance(count_raw, str) and not count_raw.strip())
            or pd.isna(count_raw)
        ):
            if strict_count:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Count cannot be empty")
            continue

        try:
            count_value = int(float(count_raw))
        except (TypeError, ValueError) as exc:
            if strict_count:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Count must be numeric") from exc
            continue

        if count_value < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Count must be non-negative")
        if not area or not issue:
            continue

        normalized.append(
            {
                "area": area,
                "issue": issue,
                "phase": phase,
                "count": count_value,
            }
        )

    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid rows found")

    return normalized


def parse_flexible_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    current_phase: Optional[str] = None
    chunks = re.split(r"[\n;]+", text)
    for chunk in chunks:
        line = chunk.strip()
        if not line:
            continue

        before_heading = re.match(
            r"^\s*(before awareness|before)\s*:?[\s\-]*(table|section)?\s*$",
            line,
            flags=re.IGNORECASE,
        )
        after_heading = re.match(
            r"^\s*(after awareness|after)\s*:?[\s\-]*(table|section)?\s*$",
            line,
            flags=re.IGNORECASE,
        )
        if before_heading:
            current_phase = "Before Awareness"
            continue
        if after_heading:
            current_phase = "After Awareness"
            continue

        structured_with_phase = re.match(
            r"^\s*([A-Za-z][A-Za-z\s\-/]{1,80})\s+([A-Za-z][A-Za-z\s/&\-]{1,80})\s+(before awareness|after awareness|before|after)\s+(\d+)\s*$",
            line,
            flags=re.IGNORECASE,
        )
        if structured_with_phase:
            rows.append(
                {
                    "area": clean_phrase(structured_with_phase.group(1)),
                    "issue": clean_phrase(structured_with_phase.group(2)),
                    "phase": standardize_phase(structured_with_phase.group(3)),
                    "count": structured_with_phase.group(4),
                }
            )
            continue

        structured_with_count = re.match(
            r"^\s*([A-Za-z][A-Za-z\s\-/]{1,80})\s+([A-Za-z][A-Za-z\s/&\-]{1,80})\s+(\d+)\s*$",
            line,
            flags=re.IGNORECASE,
        )
        if structured_with_count and current_phase:
            rows.append(
                {
                    "area": clean_phrase(structured_with_count.group(1)),
                    "issue": clean_phrase(structured_with_count.group(2)),
                    "phase": current_phase,
                    "count": structured_with_count.group(3),
                }
            )
            continue

        area = "Unspecified"
        content = line

        area_match = re.match(r"^\s*([A-Za-z][A-Za-z\s\-/]{1,80})\s*[:\-]\s*(.+)$", line)
        if area_match:
            area = clean_phrase(area_match.group(1))
            content = area_match.group(2)

        segments = [segment.strip() for segment in content.split(",") if segment.strip()]
        if not segments:
            segments = [content]

        for segment in segments:
            segment_phase = current_phase
            phase_match = re.search(
                r"\b(before awareness|after awareness|before|after)\b",
                segment,
                flags=re.IGNORECASE,
            )
            if phase_match:
                segment_phase = standardize_phase(phase_match.group(1))
                segment = re.sub(
                    r"\b(before awareness|after awareness|before|after)\b",
                    "",
                    segment,
                    count=1,
                    flags=re.IGNORECASE,
                ).strip(" :-")

            pairs = re.findall(r"([A-Za-z][A-Za-z\s/&\-]{1,80})\s*(?:=|:|\-)?\s*(\d+)", segment)
            for issue, count in pairs:
                rows.append(
                    {
                        "area": area,
                        "issue": issue,
                        "phase": segment_phase,
                        "count": count,
                    }
                )

    if not rows:
        return []
    return normalize_rows(rows)


def dataframe_to_rows(dataframe: pd.DataFrame) -> List[Dict[str, Any]]:
    normalized_columns: Dict[str, str] = {}
    for original in dataframe.columns:
        normalized_key = re.sub(r"[^a-z]", "", str(original).lower())
        normalized_columns[normalized_key] = original

    area_column = (
        normalized_columns.get("area")
        or normalized_columns.get("block")
        or normalized_columns.get("areablock")
        or normalized_columns.get("district")
    )
    issue_column = (
        normalized_columns.get("issue")
        or normalized_columns.get("issuetype")
        or normalized_columns.get("type")
    )
    phase_column = normalized_columns.get("phase")
    count_column = (
        normalized_columns.get("count")
        or normalized_columns.get("reports")
        or normalized_columns.get("number")
    )

    before_column = (
        normalized_columns.get("beforeawareness")
        or normalized_columns.get("before")
        or normalized_columns.get("preawareness")
        or normalized_columns.get("pre")
    )
    after_column = (
        normalized_columns.get("afterawareness")
        or normalized_columns.get("after")
        or normalized_columns.get("postawareness")
        or normalized_columns.get("post")
    )

    if not area_column or not issue_column:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV/XLSX must include Area and Issue columns",
        )

    rows: List[Dict[str, Any]] = []
    filled = dataframe.fillna("")

    if count_column:
        for _, row in filled.iterrows():
            rows.append(
                {
                    "area": row.get(area_column, ""),
                    "issue": row.get(issue_column, ""),
                    "phase": row.get(phase_column, None) if phase_column else None,
                    "count": row.get(count_column, None),
                }
            )
        return normalize_rows(rows, strict_count=False)

    if before_column or after_column:
        for _, row in filled.iterrows():
            if before_column:
                rows.append(
                    {
                        "area": row.get(area_column, ""),
                        "issue": row.get(issue_column, ""),
                        "phase": "Before Awareness",
                        "count": row.get(before_column, None),
                    }
                )
            if after_column:
                rows.append(
                    {
                        "area": row.get(area_column, ""),
                        "issue": row.get(issue_column, ""),
                        "phase": "After Awareness",
                        "count": row.get(after_column, None),
                    }
                )
        return normalize_rows(rows, strict_count=False)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="CSV/XLSX must include Count or Before/After Awareness columns",
    )


def extract_rows_from_pdf_text(text: str) -> List[Dict[str, Any]]:
    parsed_rows = parse_flexible_text(text)
    if parsed_rows:
        return parsed_rows

    lower_text = text.lower()
    issue_counts: Dict[str, int] = {}
    for issue in ISSUE_KEYWORDS:
        count = len(re.findall(rf"\b{re.escape(issue)}\b", lower_text))
        if count > 0:
            issue_counts[clean_phrase(issue)] = count

    if not issue_counts:
        return []

    area_rows: List[Dict[str, Any]] = []
    for area in KNOWN_AREAS:
        area_name = clean_phrase(area)
        for issue_name in issue_counts.keys():
            proximity_pattern = rf"{re.escape(area)}[^.\n]{{0,120}}{re.escape(issue_name.lower())}"
            proximity_count = len(re.findall(proximity_pattern, lower_text))
            if proximity_count > 0:
                area_rows.append(
                    {
                        "area": area_name,
                        "issue": issue_name,
                        "phase": None,
                        "count": proximity_count,
                    }
                )

    if area_rows:
        return normalize_rows(area_rows)

    fallback_rows = [
        {
            "area": "Unspecified",
            "issue": issue_name,
            "phase": None,
            "count": count,
        }
        for issue_name, count in issue_counts.items()
    ]
    return normalize_rows(fallback_rows)


def top_three_text(counter: Counter) -> str:
    ranked = [f"{name} ({count})" for name, count in counter.most_common(3)]
    text = ", ".join(ranked)
    if len(counter) > 3:
        text = f"{text}, etc"
    return text


def list_with_etc(values: List[str], limit: int = 3) -> str:
    if not values:
        return ""
    shown = values[:limit]
    text = ", ".join(shown)
    if len(values) > limit:
        text = f"{text}, etc"
    return text


def aggregate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple, int] = defaultdict(int)
    for row in rows:
        grouped[(row["area"], row["issue"], row.get("phase") or "All Phases")] += row["count"]

    aggregated = [
        {"area": area, "issue": issue, "phase": phase, "count": count}
        for (area, issue, phase), count in grouped.items()
    ]
    aggregated.sort(key=lambda item: item["count"], reverse=True)
    return aggregated


def compute_analysis(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    issue_counter: Counter = Counter()
    area_counter: Counter = Counter()
    awareness_by_area: Dict[str, Dict[str, int]] = defaultdict(lambda: {"before": 0, "after": 0})
    awareness_by_issue: Dict[str, Dict[str, int]] = defaultdict(lambda: {"before": 0, "after": 0})
    before_pair_counter: Dict[tuple, int] = defaultdict(int)
    after_pair_counter: Dict[tuple, int] = defaultdict(int)

    total_before = 0
    total_after = 0
    phase_labeled_count = 0

    for row in rows:
        issue_counter[row["issue"]] += row["count"]
        area_counter[row["area"]] += row["count"]

        if row.get("phase") == "Before Awareness":
            phase_labeled_count += 1
            awareness_by_area[row["area"]]["before"] += row["count"]
            awareness_by_issue[row["issue"]]["before"] += row["count"]
            before_pair_counter[(row["area"], row["issue"])] += row["count"]
            total_before += row["count"]
        elif row.get("phase") == "After Awareness":
            phase_labeled_count += 1
            awareness_by_area[row["area"]]["after"] += row["count"]
            awareness_by_issue[row["issue"]]["after"] += row["count"]
            after_pair_counter[(row["area"], row["issue"])] += row["count"]
            total_after += row["count"]

    issue_distribution_default = [{"name": issue_name, "value": count} for issue_name, count in issue_counter.most_common()]
    area_comparison_default = [{"area": area_name, "count": count} for area_name, count in area_counter.most_common()]

    has_both_phases = total_before > 0 and total_after > 0
    if phase_labeled_count == 0:
        phase_scope = "unphased"
    elif has_both_phases:
        phase_scope = "both"
    elif total_before > 0:
        phase_scope = "before-only"
    else:
        phase_scope = "after-only"

    unique_issues = list(issue_counter.keys())
    unique_areas = list(area_counter.keys())

    focus_mode = "mixed"
    focus_label = ""

    pie_data = issue_distribution_default
    bar_data: List[Dict[str, Any]] = [{"label": item["area"], "count": item["count"]} for item in area_comparison_default]
    line_data: List[Dict[str, Any]] = [{"label": item["area"], "value": item["count"]} for item in area_comparison_default]
    line_mode = "single"

    pie_title = "Issue Distribution (Pie)"
    bar_title = "Area Comparison (Bar)"
    line_title = "Area-Wise Trend (Line)"

    if len(unique_issues) == 1 and len(unique_areas) > 1:
        focus_mode = "single-issue-multi-area"
        focus_label = unique_issues[0]
        pie_data = [{"name": name, "value": count} for name, count in area_counter.most_common()]
        bar_data = [{"label": name, "count": count} for name, count in area_counter.most_common()]
        line_data = [{"label": name, "value": count} for name, count in area_counter.most_common()]
        pie_title = f"{focus_label} Distribution by Area (Pie)"
        bar_title = f"{focus_label} Distribution by Area (Bar)"
        line_title = f"{focus_label} Trend by Area (Line)"

    elif len(unique_areas) == 1 and len(unique_issues) > 1:
        focus_mode = "single-area-multi-issue"
        focus_label = unique_areas[0]
        pie_data = [{"name": name, "value": count} for name, count in issue_counter.most_common()]
        bar_data = [{"label": name, "count": count} for name, count in issue_counter.most_common()]
        line_data = [{"label": name, "value": count} for name, count in issue_counter.most_common()]
        pie_title = f"{focus_label}: Issue Breakdown (Pie)"
        bar_title = f"{focus_label}: Issue Comparison (Bar)"
        line_title = f"{focus_label}: Issue Trend (Line)"

    has_awareness_data = False
    if has_both_phases:
        if focus_mode == "single-issue-multi-area":
            comparable_areas = [
                area_name
                for area_name, _ in area_counter.most_common()
                if awareness_by_area[area_name]["before"] > 0 and awareness_by_area[area_name]["after"] > 0
            ]
            if comparable_areas:
                has_awareness_data = True
                line_mode = "awareness"
                pie_data = [{"name": name, "value": count} for name, count in area_counter.most_common()]
                pie_title = f"{focus_label} Distribution by Area (Pie)"
                bar_data = [
                    {
                        "label": area_name,
                        "before": awareness_by_area[area_name]["before"],
                        "after": awareness_by_area[area_name]["after"],
                    }
                    for area_name in comparable_areas
                ]
                line_data = [
                    {
                        "label": area_name,
                        "before": awareness_by_area[area_name]["before"],
                        "after": awareness_by_area[area_name]["after"],
                        "change": awareness_by_area[area_name]["before"] - awareness_by_area[area_name]["after"],
                    }
                    for area_name in comparable_areas
                ]
                bar_title = f"{focus_label}: Before vs After by Area (Bar)"
                line_title = f"{focus_label}: Before vs After by Area (Line)"

        elif focus_mode == "single-area-multi-issue":
            comparable_issues = [
                issue_name
                for issue_name, _ in issue_counter.most_common()
                if awareness_by_issue[issue_name]["before"] > 0 and awareness_by_issue[issue_name]["after"] > 0
            ]
            if comparable_issues:
                has_awareness_data = True
                line_mode = "awareness"
                pie_data = [{"name": name, "value": count} for name, count in issue_counter.most_common()]
                pie_title = f"{focus_label}: Issue Breakdown (Pie)"
                bar_data = [
                    {
                        "label": issue_name,
                        "before": awareness_by_issue[issue_name]["before"],
                        "after": awareness_by_issue[issue_name]["after"],
                    }
                    for issue_name in comparable_issues
                ]
                line_data = [
                    {
                        "label": issue_name,
                        "before": awareness_by_issue[issue_name]["before"],
                        "after": awareness_by_issue[issue_name]["after"],
                        "change": awareness_by_issue[issue_name]["before"] - awareness_by_issue[issue_name]["after"],
                    }
                    for issue_name in comparable_issues
                ]
                bar_title = f"{focus_label}: Before vs After by Issue (Bar)"
                line_title = f"{focus_label}: Before vs After by Issue (Line)"

        else:
            common_pairs = sorted(set(before_pair_counter.keys()).intersection(set(after_pair_counter.keys())))
            if common_pairs:
                area_pair_totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"before": 0, "after": 0})
                for area_name, issue_name in common_pairs:
                    area_pair_totals[area_name]["before"] += before_pair_counter[(area_name, issue_name)]
                    area_pair_totals[area_name]["after"] += after_pair_counter[(area_name, issue_name)]

                comparable_areas = sorted(
                    area_pair_totals.keys(),
                    key=lambda area_name: area_pair_totals[area_name]["before"] + area_pair_totals[area_name]["after"],
                    reverse=True,
                )
                has_awareness_data = True
                line_mode = "awareness"
                pie_data = [
                    {
                        "name": "Before Awareness",
                        "value": sum(area_pair_totals[area_name]["before"] for area_name in comparable_areas),
                    },
                    {
                        "name": "After Awareness",
                        "value": sum(area_pair_totals[area_name]["after"] for area_name in comparable_areas),
                    },
                ]
                pie_title = "Before vs After Awareness (Pie)"
                bar_data = [
                    {
                        "label": area_name,
                        "before": area_pair_totals[area_name]["before"],
                        "after": area_pair_totals[area_name]["after"],
                    }
                    for area_name in comparable_areas
                ]
                line_data = [
                    {
                        "label": area_name,
                        "before": area_pair_totals[area_name]["before"],
                        "after": area_pair_totals[area_name]["after"],
                        "change": area_pair_totals[area_name]["before"] - area_pair_totals[area_name]["after"],
                    }
                    for area_name in comparable_areas
                ]
                bar_title = "Before vs After by Area (Bar)"
                line_title = "Before vs After by Area (Line)"

    table_rows = aggregate_rows(rows)
    before_table_rows = [row for row in table_rows if row["phase"] == "Before Awareness"]
    after_table_rows = [row for row in table_rows if row["phase"] == "After Awareness"]
    unphased_table_rows = [
        row for row in table_rows if row["phase"] not in {"Before Awareness", "After Awareness"}
    ]

    top_issue = issue_distribution_default[0]["name"] if issue_distribution_default else "N/A"
    top_area = area_comparison_default[0]["area"] if area_comparison_default else "N/A"
    total_count = sum(item["value"] for item in issue_distribution_default)

    awareness_change_percent: Optional[float] = None
    if has_awareness_data and total_before > 0:
        awareness_change_percent = round(((total_before - total_after) / total_before) * 100, 2)

    insight_parts: List[str] = []

    if has_awareness_data:
        insight_parts.append(f"Before Awareness total is {total_before}, and After Awareness total is {total_after}.")

        improved_messages: List[str] = []
        worsened_messages: List[str] = []

        if focus_mode == "single-area-multi-issue":
            for issue_name, counts in awareness_by_issue.items():
                before_value = counts["before"]
                after_value = counts["after"]
                if before_value <= 0 or after_value <= 0:
                    continue
                if after_value < before_value:
                    improved_messages.append(
                        f"awareness is working for {issue_name} in {focus_label} ({before_value}→{after_value})"
                    )
                elif after_value > before_value:
                    worsened_messages.append(
                        f"need more effort in {focus_label} for {issue_name} ({before_value}→{after_value})"
                    )
        else:
            subject = focus_label if focus_mode == "single-issue-multi-area" else "this dataset"
            if focus_mode == "mixed":
                comparable_area_rows = [
                    (
                        item.get("label", ""),
                        int(item.get("before", 0)),
                        int(item.get("after", 0)),
                    )
                    for item in line_data
                    if item.get("before") is not None and item.get("after") is not None
                ]
            else:
                comparable_area_rows = [
                    (
                        area_name,
                        counts["before"],
                        counts["after"],
                    )
                    for area_name, counts in awareness_by_area.items()
                ]

            for area_name, before_value, after_value in comparable_area_rows:
                if before_value <= 0 or after_value <= 0:
                    continue
                if after_value < before_value:
                    improved_messages.append(
                        f"awareness is working in {area_name} for {subject} ({before_value}→{after_value})"
                    )
                elif after_value > before_value:
                    worsened_messages.append(
                        f"need more effort in {area_name} for {subject} ({before_value}→{after_value})"
                    )

        if improved_messages:
            insight_parts.append(f"Positive trend: {list_with_etc(improved_messages)}.")
        if worsened_messages:
            insight_parts.append(f"Needs improvement: {list_with_etc(worsened_messages)}.")
        if not improved_messages and not worsened_messages:
            insight_parts.append("Before and after values are equal, so awareness impact is currently neutral.")

    elif phase_scope == "both":
        if focus_mode == "single-issue-multi-area":
            insight_parts.append(
                f"Before and After data are present, but exact matching area/issue pairs were not found for direct comparison of {focus_label}."
            )
            insight_parts.append(f"Current {focus_label} area distribution: {top_three_text(area_counter)}.")
        elif focus_mode == "single-area-multi-issue":
            insight_parts.append(
                f"Before and After data are present, but exact matching area/issue pairs were not found for direct comparison in {focus_label}."
            )
            insight_parts.append(f"Current issue distribution in {focus_label}: {top_three_text(issue_counter)}.")
        else:
            insight_parts.append(
                "Before and After data are present, but exact matching area/issue pairs were not found for direct comparison."
            )

    elif focus_mode == "single-issue-multi-area":
        phase_text = "Before Awareness" if phase_scope == "before-only" else "After Awareness" if phase_scope == "after-only" else "Current"
        insight_parts.append(f"{phase_text} data for {focus_label} across areas: {top_three_text(area_counter)}.")
        if top_area != "N/A":
            insight_parts.append(f"{top_area} needs more awareness campaign for {focus_label}.")
    elif focus_mode == "single-area-multi-issue":
        phase_text = "Before Awareness" if phase_scope == "before-only" else "After Awareness" if phase_scope == "after-only" else "Current"
        insight_parts.append(f"{phase_text} issue distribution in {focus_label}: {top_three_text(issue_counter)}.")
        if top_issue != "N/A":
            insight_parts.append(f"{focus_label} needs more awareness on {top_issue} because it is highest.")
    else:
        insight_parts.extend([
            f"{top_area} area shows the highest total reports.",
            f"{top_issue} is the most frequently reported issue in this dataset.",
        ])
# ===== FINAL SMART INSIGHT =====

change = total_before - total_after

percentage = 0
if total_before > 0:
    percentage = round((change / total_before) * 100)

# ===== IMPROVEMENT =====
if change > 0:
    if percentage >= 50:
        tone = "strong improvement"
        suggestion_text = "Scale this awareness model to other areas."
    elif percentage >= 20:
        tone = "good improvement"
        suggestion_text = "Continue campaigns and expand reach."
    else:
        tone = "slight improvement"
        suggestion_text = "Need stronger awareness efforts and better targeting."

    insight_text = (
        f"{top_issue} issues reduced by {percentage}% in {top_area} after awareness, "
        f"showing {tone}. {suggestion_text}"
    )

# ===== WORSENING =====
elif change < 0:
    percentage = abs(percentage)

    if percentage >= 50:
        tone = "serious worsening"
        suggestion_text = "Urgent intervention required. Current strategy is failing."
    elif percentage >= 20:
        tone = "noticeable increase"
        suggestion_text = "Revise awareness strategy and improve execution."
    else:
        tone = "slight increase"
        suggestion_text = "Monitor closely and improve campaign effectiveness."

    insight_text = (
        f"{top_issue} issues increased by {percentage}% in {top_area} after awareness, "
        f"indicating {tone}. {suggestion_text}"
    )

# ===== NO CHANGE =====
else:
    insight_text = (
        f"No change observed in {top_issue} issues in {top_area} after awareness. "
        f"Awareness efforts are not impactful. Strategy needs improvement."
    )

# ===== NO DATA =====
if total_before == 0 and total_after == 0:
    insight_text = "Insufficient data to measure awareness impact. Collect proper data."

    
    return {
        "summary": {
            "total_count": total_count,
            "top_issue": top_issue,
            "top_area": top_area,
            "awareness_change_percent": awareness_change_percent,
            "before_total": total_before,
            "after_total": total_after,
        },
        "chart_data": {
            "focus_mode": focus_mode,
            "focus_label": focus_label,
            "phase_scope": phase_scope,
            "pie_data": pie_data,
            "bar_data": bar_data,
            "line_data": line_data,
            "line_mode": line_mode,
            "has_awareness_data": has_awareness_data,
            "pie_title": pie_title,
            "bar_title": bar_title,
            "line_title": line_title,
            "table_rows": table_rows,
            "phase_tables": {
                "before": before_table_rows,
                "after": after_table_rows,
                "unphased": unphased_table_rows,
            },
        },
        "insight": insight_text,
    }


async def create_analysis_record(
    user_id: str,
    source_type: str,
    title: str,
    rows: List[Dict[str, Any]],
    computed_result: Dict[str, Any],
    file_metadata: Optional[Dict[str, Any]] = None,
    raw_input_excerpt: Optional[str] = None,
) -> Dict[str, Any]:
    analysis_doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "source_type": source_type,
        "title": title,
        "rows": rows,
        "summary": computed_result["summary"],
        "chart_data": computed_result["chart_data"],
        "insight": computed_result["insight"],
        "file_metadata": file_metadata,
        "raw_input_excerpt": raw_input_excerpt,
        "created_at": now_iso(),
    }
    await db.analyses.insert_one({**analysis_doc})
    return analysis_doc


def build_csv_stream(rows: List[Dict[str, Any]], fieldnames: List[str]) -> io.BytesIO:
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return io.BytesIO(csv_buffer.getvalue().encode("utf-8"))


@api_router.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Community Awareness Data Platform API"}


@api_router.post("/auth/register", response_model=AuthResponse)
async def register_user(payload: UserRegisterRequest) -> AuthResponse:
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "full_name": payload.full_name.strip() if payload.full_name else "",
        "password_hash": hash_password(payload.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one({**user_doc})

    user_public = {
        "id": user_doc["id"],
        "email": user_doc["email"],
        "full_name": user_doc["full_name"],
        "created_at": user_doc["created_at"],
    }
    token = create_access_token(subject=user_doc["id"], role="user")
    return AuthResponse(token=token, user=UserPublic(**user_public))


@api_router.post("/auth/login", response_model=AuthResponse)
async def login_user(payload: UserLoginRequest) -> AuthResponse:
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(subject=user["id"], role="user")
    user_public = {
        "id": user["id"],
        "email": user["email"],
        "full_name": user.get("full_name", ""),
        "created_at": user["created_at"],
    }
    return AuthResponse(token=token, user=UserPublic(**user_public))


@api_router.get("/auth/me", response_model=UserPublic)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> UserPublic:
    return UserPublic(**current_user)


@api_router.post("/admin/login", response_model=AdminAuthResponse)
async def admin_login(payload: AdminLoginRequest) -> AdminAuthResponse:
    admin_settings = await db.admin_settings.find_one({}, {"_id": 0})
    username = payload.username.strip()
    password = payload.password

    stored_valid = (
        bool(admin_settings)
        and username == admin_settings.get("username", "")
        and verify_password(password, admin_settings.get("password_hash", ""))
    )
    default_valid = username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD

    if not stored_valid and not default_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")

    resolved_username = admin_settings["username"] if stored_valid else DEFAULT_ADMIN_USERNAME
    token = create_access_token(subject=resolved_username, role="admin")
    return AdminAuthResponse(token=token, username=resolved_username)


@api_router.post("/admin/change-password", response_model=MessageResponse)
async def change_admin_password(
    payload: AdminPasswordChangeRequest,
    admin_settings: Dict[str, Any] = Depends(get_current_admin),
) -> MessageResponse:
    old_matches_stored = verify_password(payload.old_password, admin_settings["password_hash"])
    old_matches_default = payload.old_password == DEFAULT_ADMIN_PASSWORD
    if not old_matches_stored and not old_matches_default:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Old password is incorrect")

    update_data: Dict[str, Any] = {
        "password_hash": hash_password(payload.new_password),
        "updated_at": now_iso(),
    }
    if payload.new_username and payload.new_username.strip():
        update_data["username"] = payload.new_username.strip()

    await db.admin_settings.update_one({}, {"$set": update_data})
    return MessageResponse(message="Admin credentials updated successfully")


@api_router.post("/analysis/manual", response_model=AnalysisResult)
async def analyze_manual_data(
    payload: ManualAnalyzeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AnalysisResult:
    rows = normalize_rows([item.model_dump() for item in payload.rows])
    computed = compute_analysis(rows)
    analysis_doc = await create_analysis_record(
        user_id=current_user["id"],
        source_type="manual",
        title=payload.title or "Manual Entry Analysis",
        rows=rows,
        computed_result=computed,
    )
    return AnalysisResult(**analysis_doc)


@api_router.post("/analysis/text", response_model=AnalysisResult)
async def analyze_text_data(
    payload: TextAnalyzeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AnalysisResult:
    rows = parse_flexible_text(payload.text)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse text. Use format like: Area : issue 2, issue 3",
        )
    computed = compute_analysis(rows)
    analysis_doc = await create_analysis_record(
        user_id=current_user["id"],
        source_type="text",
        title=payload.title or "Text Input Analysis",
        rows=rows,
        computed_result=computed,
        raw_input_excerpt=payload.text[:400],
    )
    return AnalysisResult(**analysis_doc)


@api_router.post("/analysis/file", response_model=AnalysisResult)
async def analyze_file_data(
    file: UploadFile = File(...),
    title: str = Form("File Upload Analysis"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AnalysisResult:
    filename = file.filename or "uploaded_file"
    extension = filename.lower().split(".")[-1] if "." in filename else ""
    file_bytes = await file.read()

    rows: List[Dict[str, Any]]
    raw_input_excerpt: Optional[str] = None

    try:
        if extension == "csv":
            dataframe = pd.read_csv(io.BytesIO(file_bytes))
            rows = dataframe_to_rows(dataframe)
        elif extension == "xlsx":
            dataframe = pd.read_excel(io.BytesIO(file_bytes))
            rows = dataframe_to_rows(dataframe)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Upload CSV or XLSX only",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"File parsing failed: {exc}") from exc

    computed = compute_analysis(rows)
    metadata = {
        "filename": filename,
        "content_type": file.content_type,
        "size_bytes": len(file_bytes),
        "uploaded_at": now_iso(),
    }

    analysis_doc = await create_analysis_record(
        user_id=current_user["id"],
        source_type="file",
        title=title or "File Upload Analysis",
        rows=rows,
        computed_result=computed,
        file_metadata=metadata,
        raw_input_excerpt=raw_input_excerpt,
    )
    return AnalysisResult(**analysis_doc)


@api_router.get("/analysis/history", response_model=List[AnalysisResult])
async def get_analysis_history(current_user: Dict[str, Any] = Depends(get_current_user)) -> List[AnalysisResult]:
    records = await db.analyses.find(
        {"user_id": current_user["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)
    return [AnalysisResult(**record) for record in records]


@api_router.get("/analysis/history/{analysis_id}", response_model=AnalysisResult)
async def get_analysis_detail(
    analysis_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AnalysisResult:
    record = await db.analyses.find_one(
        {"id": analysis_id, "user_id": current_user["id"]},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found")
    return AnalysisResult(**record)


@api_router.delete("/analysis/history/{analysis_id}", response_model=MessageResponse)
async def delete_analysis_record(
    analysis_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> MessageResponse:
    result = await db.analyses.delete_one({"id": analysis_id, "user_id": current_user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis record not found")
    return MessageResponse(message="Analysis record deleted")


@api_router.post("/community/submit", response_model=CommunitySubmissionResponse)
async def submit_community_data(
    payload: CommunitySubmissionCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> CommunitySubmissionResponse:
    submission = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "area": clean_phrase(payload.area),
        "issue_type": clean_phrase(payload.issue_type),
        "description": payload.description.strip(),
        "created_at": now_iso(),
    }
    await db.community_submissions.insert_one({**submission})
    return CommunitySubmissionResponse(**submission)


@api_router.get("/community/mine", response_model=List[CommunitySubmissionResponse])
async def get_my_community_submissions(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[CommunitySubmissionResponse]:
    records = await db.community_submissions.find(
        {"user_id": current_user["id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(1000)
    return [CommunitySubmissionResponse(**record) for record in records]


@api_router.get("/admin/submissions", response_model=List[CommunitySubmissionResponse])
async def admin_get_submissions(_: Dict[str, Any] = Depends(get_current_admin)) -> List[CommunitySubmissionResponse]:
    records = await db.community_submissions.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [CommunitySubmissionResponse(**record) for record in records]


@api_router.delete("/admin/submissions/{submission_id}", response_model=MessageResponse)
async def admin_delete_submission(
    submission_id: str,
    _: Dict[str, Any] = Depends(get_current_admin),
) -> MessageResponse:
    result = await db.community_submissions.delete_one({"id": submission_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return MessageResponse(message="Submission deleted")


@api_router.get("/admin/datasets", response_model=List[AnalysisResult])
async def admin_get_datasets(_: Dict[str, Any] = Depends(get_current_admin)) -> List[AnalysisResult]:
    records = await db.analyses.find({"source_type": "file"}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return [AnalysisResult(**record) for record in records]


@api_router.delete("/admin/analyses/{analysis_id}", response_model=MessageResponse)
async def admin_delete_analysis(
    analysis_id: str,
    _: Dict[str, Any] = Depends(get_current_admin),
) -> MessageResponse:
    result = await db.analyses.delete_one({"id": analysis_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return MessageResponse(message="Analysis record deleted")


@api_router.get("/admin/export/submissions")
async def admin_export_submissions(_: Dict[str, Any] = Depends(get_current_admin)) -> StreamingResponse:
    submissions = await db.community_submissions.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    fields = ["id", "user_id", "user_email", "area", "issue_type", "description", "created_at"]
    stream = build_csv_stream(submissions, fields)
    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=community_submissions.csv"},
    )


@api_router.get("/admin/export/datasets")
async def admin_export_datasets(_: Dict[str, Any] = Depends(get_current_admin)) -> StreamingResponse:
    datasets = await db.analyses.find({"source_type": "file"}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    export_rows: List[Dict[str, Any]] = []
    for item in datasets:
        export_rows.append(
            {
                "id": item.get("id", ""),
                "user_id": item.get("user_id", ""),
                "source_type": item.get("source_type", ""),
                "title": item.get("title", ""),
                "created_at": item.get("created_at", ""),
                "row_count": len(item.get("rows", [])),
                "filename": (item.get("file_metadata") or {}).get("filename", ""),
                "size_bytes": (item.get("file_metadata") or {}).get("size_bytes", ""),
            }
        )
    fields = [
        "id",
        "user_id",
        "source_type",
        "title",
        "created_at",
        "row_count",
        "filename",
        "size_bytes",
    ]
    stream = build_csv_stream(export_rows, fields)
    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=uploaded_datasets.csv"},
    )


@app.on_event("startup")
async def ensure_admin_credentials() -> None:
    existing_admin = await db.admin_settings.find_one({}, {"_id": 0})
    if not existing_admin:
        await db.admin_settings.insert_one(
            {
                "username": DEFAULT_ADMIN_USERNAME,
                "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        )


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client() -> None:
    client.close()
