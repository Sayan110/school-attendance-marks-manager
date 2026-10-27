# School Attendance & Marks Manager

An offline Windows desktop application for the Computer Science teacher at
**SHIKSHA VIKASH ENGLISH HIGH SCHOOL** (SEBA Board, Assam). It manages Class 9
and Class 10 students, daily attendance, examination marks, analytics and
printable reports. Everything is stored locally in SQLite — no internet, no
account, no cloud service and no paid API is required at any point.

## At a glance

| Item | Value |
| --- | --- |
| Supported platform | **Windows 10 / Windows 11 (64-bit)** |
| Language / GUI | Python 3.11+ · PySide6 (Qt 6) |
| Storage | SQLite database file (local, single user) |
| Analytics | Matplotlib charts |
| Reports | ReportLab (PDF) · OpenPyXL / Pandas (Excel and CSV) |
| Packaging | PyInstaller, one-folder *windowed* build |
| Tests | pytest + pytest-cov — **217 passed, 83% coverage** (see `TEST_RESULTS.md`) |
| Network | None. The app runs fully offline after installation. |

No screenshots are included in this repository: screenshots of the running app
can contain real student names, roll numbers or marks. Verified behaviour is
documented in `TEST_RESULTS.md` instead.

---

## 1. Quick start

| Step | What to do |
| --- | --- |
| 1. Install once | Double-click **`setup.bat`**. It creates `.venv`, installs the Python packages and runs a smoke test. |
| 2. Start the app | Double-click **`run_app.bat`** (or the desktop shortcut, once created). |
| 3. Build the EXE | Double-click **`build_exe.bat`** (optional; see §3). |
| 4. Desktop shortcut | Right-click **`create_desktop_shortcut.ps1`** → *Run with PowerShell*, or run the command in §3. |

The first launch creates the database and seeds the active academic session
(2026–2027). No students or marks are invented — every list starts empty and
shows a clear empty state until you add real data.

---

## 2. Running from source

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Useful developer commands:

```bat
python main.py --smoke-test                     :: build every page on a temp DB, then exit
python main.py --screenshots C:\temp\shots      :: render every page to PNG files
python main.py --allow-multiple                 :: skip the single-instance check
python -m pytest tests -q                       :: run the automated test suite
python -m pytest tests -q --cov=app --cov-report=term   :: with coverage
```

Python 3.11 or newer is recommended (developed and tested with Python 3.13.3,
PySide6 6.12).

Verified on this machine: `python main.py --smoke-test` prints
`smoke-test: all pages built and refreshed` / `smoke-test: OK` and exits with
code 0.

---

## 3. Building the standalone EXE and the shortcut

```bat
build_exe.bat
powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
```

* Build output: `dist\SchoolAttendanceManager\SchoolAttendanceManager.exe`
  (a *windowed* build — no console window appears).
  The folder is about 298 MB and the EXE about 26 MB; `dist/` is intentionally
  ignored by Git. Publish the executable as a GitHub Release instead of
  committing it.
* The shortcut is created on the current user's Desktop as
  **“School Attendance & Marks Manager”**.
* `create_desktop_shortcut.ps1` prefers the packaged EXE. If the EXE has not
  been built yet it falls back to `.venv\Scripts\pythonw.exe main.py`, so the
  shortcut still works on a source checkout.
* `remove_desktop_shortcut.ps1` removes only the shortcut.
* The EXE is a one-folder build; keep the whole
  `dist\SchoolAttendanceManager` folder together if you copy it to another PC.

> The application can always be started again later: data is stored outside the
> install folder (see §4), so rebuilding or moving the app never loses records.

---

## 4. Where the data lives

| Item | Location |
| --- | --- |
| Database | `%LOCALAPPDATA%\ShikshaVikashSchoolManager\data\school_manager.db` |
| Automatic backups | `%LOCALAPPDATA%\ShikshaVikashSchoolManager\backups\` |
| Exports | `%LOCALAPPDATA%\ShikshaVikashSchoolManager\exports\` |
| Logs | `%LOCALAPPDATA%\ShikshaVikashSchoolManager\logs\` |

The install folder is never used for school data, so the app also works when it
is installed under `Program Files`. `SVSM_DATA_DIR` can override the base folder
for testing; normal users never need it.

Only one copy of the app can run at a time. Opening it a second time brings the
existing window to the front instead of starting a duplicate (this is enforced
with a lock file plus a local socket, and recovers automatically after a crash).

---

## Privacy and data safety — read before publishing

This application is intended to hold **real student records**: names, roll
numbers, guardians' names and contact numbers, attendance and examination marks.
Those records are private personal data and must never be uploaded to GitHub.

* The live database, backups and exports live **outside** this folder, under
  `%LOCALAPPDATA%\ShikshaVikashSchoolManager\` (see the table above). Copying or
  publishing the source folder therefore does not copy school data.
* The repository `.gitignore` excludes SQLite files (`*.db`, `*.sqlite`,
  `*.sqlite3`, WAL/SHM files), `backups/`, `exports/`, `*.csv`, `*.xlsx`,
  `*.pdf`, screenshots, logs, `.env` files and local secrets.
* `.gitignore` only protects files it can see. Before every commit or push, run
  `git status --short` and check that no database, backup, export or screenshot
  is staged. Never use `git add -f` on data files.
* Backups contain the same personal data as the database. Keep them on
  encrypted or access-controlled media and share them only with authorised
  school staff.
* If student data is ever committed by mistake, removing the file in a later
  commit is **not** enough — it stays in Git history. Treat it as a data
  incident: rotate/delete the repository or rewrite history, and inform the
  school.

---

## 5. What each page does

### Dashboard
Session overview: student counts for Class 9 and Class 10, today's attendance,
recent examinations, attendance and pass-rate charts, and quick links. All
numbers come from saved records only.

### Students
* Add, edit, archive (soft delete) and restore students.
* Fields: roll number, full name, class (9/10), section, guardian, contact,
  admission date, status, remarks.
* Roll numbers are unique per class and session; case variants (`9a` / `9A`)
  are normalised so they cannot bypass the duplicate check.
* Search, filter by class/section/status, sortable columns and pagination.
* Excel/CSV import with validation and a downloadable sample template;
  invalid rows are reported instead of silently dropped. Excel/CSV export.
* Archived students keep their history but are excluded from active lists.

### Attendance
* Daily register per class and date with **P** (present), **A** (absent) and
  **L** (leave). Keyboard: select rows and press `P`, `A` or `L`.
* Bulk “mark all present”, duplicate-safe saving, and a warning before
  overwriting an already saved register.
* Unsaved-changes indicator; switching class/date with pending edits asks first.
* Holidays can be recorded and are excluded from teaching-day counts.
* Daily / weekly / monthly / date-range summaries and per-student history.
* **Attendance % = Present ÷ (Present + Absent)** by default. Leave is excluded
  from the denominator. The rule is configurable in Settings
  (“Exclude leave from attendance percentage”) and is stated on the page and in
  report footnotes. Sessions that were never marked are **not** counted as
  absences.

### Marks
* Configurable examinations: type, class, date, theory/practical/project
  maxima, pass percentage, pass marks and grade scale.
* Marks entry with per-student status: **pending**, **entered**, **absent**,
  **exempted**. Pending/absent/exempted rows are never treated as zero.
* Automatic total, percentage, pass/fail and rank. Ranking is *competition*
  ranking, so ties share a rank (1, 2, 2, 4).
* Grade scales are generic and editable; they are **not** an official SEBA
  grading table and the UI says so.
* Excel/CSV import (validated, with template) and Excel/PDF export.

### Analytics
Attendance pie, results pie, marks distribution, class comparison, monthly
attendance trend, individual student performance, and summary statistics.
Charts are drawn from the selected session/examination using the same
calculation services as the reports. Empty ranges show an empty state instead of
a fabricated chart.

### Reports
Ten A4 report types, each printable and exportable to PDF, Excel and CSV, with
an on-screen preview:

1. Daily attendance register
2. Monthly attendance register
3. Individual student attendance report
4. Class attendance summary
5. Examination marksheet
6. Individual student progress report
7. Class performance report
8. Failed-student and academic-support report
9. Students below attendance threshold
10. Academic session summary

Every page carries the school name, subject, session and teacher details, plus
a footer that identifies the app. Previews use the A4 print layout, not a
screen-only approximation.

### Backup
* Manual “Back up now” using SQLite's online backup API (safe while the app is
  open).
* Automatic backups every *N* days (configurable) on startup, with retention.
* Restore validates the chosen file first, makes a `before_restore` safety copy,
  then reconnects the database. Invalid or foreign files are rejected.

### Settings
School name, teacher name/designation, subject, board, active session, attendance
and performance thresholds, default pass percentage, leave policy, grade scale,
theme (light/dark), backup folder/interval/retention, export folder and report
footer. Changing the theme rebuilds the interface immediately.

Keyboard: `F5` refreshes the current page, `Ctrl+Q` quits, `P`/`A`/`L` set status
in the attendance table.

---

## 6. Backups and moving to another PC

1. Open **Backup** and press **Back up now**; note the folder shown at the top.
2. Copy the `.db` backup file to a USB drive.
3. On the new PC install the app, open **Backup → Restore**, choose the file and
   confirm. A `before_restore` copy of the current database is kept automatically.

Backups contain personal student data. Store and share them responsibly.

---

## 7. Tests

```bat
python -m pytest tests -q
```

The suite uses temporary databases (`tmp_path`) and the offscreen Qt platform;
it never touches `%LOCALAPPDATA%` or a real school database. All student names
and phone numbers in the tests are fictional. It covers calculations, validators,
students, attendance, marks, analytics, reports, Excel/CSV import-export,
settings, backups, dates, UI wiring and the single-instance lock.

Latest run on this machine: **217 passed, 0 failed, 0 skipped** with **83% coverage**
(see `TEST_RESULTS.md` for the exact commands, output and coverage table).
The suite also verifies that closing the window stops every page timer before the
database closes, so no connection is reopened after shutdown.

---

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| “Python was not found” when using `run_app.bat` | Run `setup.bat` first, or install Python 3.11+ with “Add python.exe to PATH”. |
| App does not start, no window | Run `python main.py` from a console to see the error; check `%LOCALAPPDATA%\ShikshaVikashSchoolManager\logs`. |
| “Already running” but no window is visible | The previous window is minimised or on another monitor; use Alt+Tab. The app recovers a stale lock automatically after a crash. |
| Shortcut icon is blank | Re-run `build_exe.bat` (it bundles `app.ico`), then re-run `create_desktop_shortcut.ps1`. |
| Excel import rejects rows | Download the sample template from the import dialog and match its column headings. |
| Antivirus flags the EXE | PyInstaller executables are sometimes flagged heuristically; add an exclusion or use `run_app.bat` as the fallback. |

---

## 9. Known limitations

* Single-teacher, single-machine design: no multi-user login or network sync.
* Classes are fixed to 9 and 10, subject to Computer Science, per the school's
  requirement.
* Grade scales are configurable placeholders, not an official SEBA table.
* The packaged build is one-folder (about **298 MB** on disk because of Qt,
  matplotlib and pandas; the EXE itself is about 26 MB). This is expected for
  PyInstaller.
* Verified on Windows 10/11 only; macOS and Linux were not tested. Printing on a
  physical printer was not tested (preview and PDF generation are verified).
* Reports are A4-portrait only.
