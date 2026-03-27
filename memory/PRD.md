# PRD - Social Impact Observatory

## Original Problem Statement (User Intent)
- Build a professional community data analytics web platform for awareness research.
- Platform must collect and analyze data only (not solve social problems).
- Each user must see only their own analysis/history (strict dataset isolation).
- No separate result page: analysis must render below the same input section.
- Inputs: manual rows, flexible text, file upload (CSV/XLSX).
- Add user auth (register/login), private history, community submission form.
- Add admin login/dashboard with default credentials and global management/export.
- Improve chart clarity (no overlapping labels) and phase-aware logic:
  - Before-only data → analyze only Before.
  - After-only data → analyze only After.
  - Both phases → explicit Before vs After comparison and insights.

## Architecture Decisions
- **Frontend:** React (single-page app), Shadcn UI, Recharts, Sonner, jsPDF/html2canvas.
- **Backend:** FastAPI + Motor (MongoDB).
- **Auth:** JWT for user/admin sessions, bcrypt hashing.
- **Isolation rule:** all user analysis queries filtered by `user_id`; admin-only global routes.
- **Chart rendering stability:** switched to measured chart canvas (ResizeObserver-based) to prevent Recharts width/height warnings and overlap issues.

## What Has Been Implemented
- User registration/login (`/api/auth/register`, `/api/auth/login`, `/api/auth/me`).
- Admin login with default credentials fallback + admin credential update.
- Manual, text, and file analysis APIs with persisted records and per-user history.
- File upload restricted to **CSV/XLSX only** (PDF rejected).
- Dynamic analysis modes:
  - Single issue + multi-area
  - Single area + multi-issue
  - Mixed datasets
  - Phase scope: before-only / after-only / both / unphased
- For **all input methods** (manual, text, file):
  - one issue + many areas => area-wise distribution analysis
  - one area + many issues => issue-wise distribution analysis
- If both phases exist, charts compare Before vs After (pie/bar/line) and insights identify improvement vs needs-more-effort areas/issues.
- Structured table sections with headings: **Before Awareness Table** / **After Awareness Table** when applicable.
- File parser now supports both long format (`Area,Issue,Phase,Count`) and wide phase columns (`Area,Issue,Before Awareness,After Awareness`).
- Text parser now supports phase headings and structured lines (e.g., `Before Awareness: ...`, `Area : issue count`, and `Area Issue Before Awareness Count`).
- Comparison safety hardened: if Before/After records do not have exact matching pairs required for comparison, system does not assume missing values as zero.
- Download options: combined report PDF + individual chart/table PDFs.
- Community submission form + user submissions.
- Admin dashboard: view/delete submissions, view/delete uploaded datasets, export CSV reports.
- UI polish for readability, spacing, responsive behavior, and non-overlapping chart labels.

## Prioritized Backlog
### P0
- Add pagination/filter/search for large admin tables.
- Add stricter validation and user-friendly parse error hints for complex text input.

### P1
- Add saved analysis tags/folders for user history organization.
- Add export to Excel for full analysis report.

### P2
- Add optional advanced chart customization (stacked/grouped toggles).
- Add multilingual UI text support.

## Next Tasks
1. Add history filters (source type/date/keyword).
2. Add admin table pagination and debounced search.
3. Add richer insight templates with top-3 positives and top-3 improvement areas.