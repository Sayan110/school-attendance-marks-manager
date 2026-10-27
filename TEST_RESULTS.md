# Test Results — School Attendance & Marks Manager

Verified on **27 October 2026** on the build machine.

| Item | Value |
| --- | --- |
| Project root | `C:\Users\asus\Downloads\school-attendance-manager` |
| Python | 3.13.3 |
| PySide6 | 6.12.0 |
| PyInstaller | 6.22.3 |
| Database used by tests | temporary SQLite files under pytest `tmp_path` |
| Real school database | never opened by the tests |

---

## 1. Automated test suite

Command (from the project root):

```bat
python -m pytest tests -q
```

Actual output:

```text
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
.                                                                        [100%]
217 passed in 31.89s
```

| Passed | Failed | Skipped | Errors | Exit code |
| ---: | ---: | ---: | ---: | ---: |
| **217** | **0** | **0** | **0** | **0** |

No `ResourceWarning: unclosed database` appears in this run. Before the
shutdown fix in `app/ui/main_window.py` (`_stop_background_timers`), the same run
printed one unclosed-database warning per full-suite execution. The new
regression test `tests/test_ui.py::test_closing_window_stops_pending_timers_and_database`
was confirmed to fail when the timer shutdown is disabled, and to pass with the
fix in place.

---

## 2. Coverage

Command:

```bat
python -m pytest tests --cov=app --cov-report=term
```

Actual output (summary):

```text
============================ 217 passed in 41.92s =============================
TOTAL                                 7214   1219    83%
```

| Metric | Result |
| --- | --- |
| Statements | 7,214 |
| Missed | 1,219 |
| **Total coverage** | **83%** |

Modules below 80% (kept visible rather than hidden):

| Module | Coverage |
| --- | ---: |
| `app\ui\attendance.py` | 64% |
| `app\ui\backup.py` | 70% |
| `app\ui\settings_page.py` | 70% |
| `app\database.py` | 75% |
| `app\ui\widgets.py` | 75% |
| `app\ui\common.py` | 78% |
| `app\ui\reports_page.py` | 79% |

These are mostly large Qt form/dialog surfaces whose remaining branches are
manual-interaction paths (native file dialogs, print dialogs, drag-enabled table
editing). They are exercised by the offscreen UI tests where practical.

---

## 3. Source smoke test

Command (isolated data directory so the teacher's real database is untouched):

```bat
set SVSM_DATA_DIR=%TEMP%\svsm-smoke-final
python main.py --smoke-test
```

Actual output:

```text
smoke-test: all pages built and refreshed
smoke-test: OK
EXIT=0
```

The smoke test builds the main window, every page, applies the theme and refreshes
each page against a temporary database, then closes cleanly.

---

## 4. Packaged executable

Build command:

```bat
build_exe.bat
```

Result: **Build complete** (PyInstaller one-folder build).

| Item | Value |
| --- | --- |
| EXE | `C:\Users\asus\Downloads\school-attendance-manager\dist\SchoolAttendanceManager\SchoolAttendanceManager.exe` |
| EXE size | 26,408,030 bytes (≈ 26.4 MB) |
| Folder size | 298.4 MB |
| Console window | none (windowed build) |

### 4.1 Packaged smoke test

```bat
dist\SchoolAttendanceManager\SchoolAttendanceManager.exe --smoke-test
```

with `SVSM_DATA_DIR` pointed at a temporary folder:

```text
EXIT=0
smoke-test: all pages built and refreshed
smoke-test: OK
STDERR_BYTES=0
```

### 4.2 Window, single instance, close and reopen

Data was seeded through the application's own services
(`AppContext` → `StudentService`) before launching the packaged EXE, so the
persistence check covers real records.

```text
SEEDED_COUNT=1
FIRST_TITLE=School Attendance & Marks Manager
SECOND_EXITED=True
FIRST_ALIVE=True
PROCESS_COUNT=1
FIRST_EXITED_AFTER_CLOSE=True
PROCESSES_AFTER_CLOSE=0
REOPEN_TITLE=School Attendance & Marks Manager
DB_EXISTS=True
DB_SIZE=131072
REOPEN_EXITED=True
VERIFY_COUNT=1
FOUND=True
```

Interpretation:

* The GUI opens with the correct window title.
* A second launch exits by itself and the first window stays alive: exactly one
  process remains (`PROCESS_COUNT=1`), so the single-instance lock and activation
  socket work.
* Closing the main window terminates the process (`PROCESSES_AFTER_CLOSE=0`);
  no background/zombie process is left.
* Reopening shows the window again, the SQLite file is intact (131,072 bytes) and
  the student created before the first launch is still present after the reopen.

---

## 5. Desktop shortcut

Creation command:

```bat
powershell -ExecutionPolicy Bypass -File create_desktop_shortcut.ps1
```

Actual result:

```text
Created shortcut: C:\Users\asus\OneDrive\Desktop\School Attendance & Marks Manager.lnk
Launch target:    C:\Users\asus\Downloads\school-attendance-manager\dist\SchoolAttendanceManager\SchoolAttendanceManager.exe
Mode:             packaged EXE
Working folder:   C:\Users\asus\Downloads\school-attendance-manager\dist\SchoolAttendanceManager
Icon:             C:\Users\asus\Downloads\school-attendance-manager\app.ico,0
```

Verification by reading the `.lnk` file and launching it:

```text
SHORTCUT_NAME=School Attendance & Marks Manager
TARGET_IS_EXE=True
TARGET_EXISTS=True
ARGUMENTS=[]
WORKDIR_OK=True
ICON_OK=True
NO_CONSOLE_ENGINE=windowed-exe
SHORTCUT_TITLE=School Attendance & Marks Manager
SHORTCUT_EXITED=True
PROCESSES_AFTER_CLOSE=0
DB_EXISTS=True
SHORTCUT_REOPEN_TITLE=School Attendance & Marks Manager
SHORTCUT_REOPEN_EXITED=True
```

The shortcut points at the packaged EXE (not the source folder), uses the bundled
`app.ico`, starts in the packaged application folder, opens the GUI, closes
cleanly, and works again after being closed and reopened. The packaged build is
windowed, so no console window appears.

---

## 6. Shutdown / resource cleanup

* `app/ui/shutdown.py::shutdown_qt()` deletes top-level widgets, flushes
  `DeferredDelete` events and quits the Qt application for both the real app and
  the test session. Before this change the interpreter intermittently aborted at
  exit (0xC0000409 / 0xC0000005); successive runs now exit with code 0.
* `MainWindow.closeEvent()` now stops every child `QTimer` before the database
  closes. A debounce timer that fired after shutdown previously triggered a page
  refresh, which reopened a closed database and leaked the connection.
* `Database.close()` still commits, runs `PRAGMA optimize`, closes the connection
  and clears it; `AppContext.close()` is the single owner of that lifecycle.
* The single-instance `QLockFile` and `QLocalServer` are released on exit;
  verified by the second launch exiting while the first stays alive, and by a
  clean relaunch after closing.

No forced process termination is used in production code.

---

## 7. Remaining limitations

* The UI layer has the lowest coverage (`attendance.py` 64%,
  `settings_page.py` 70%, `backup.py` 70%). The uncovered lines are mostly
  native-dialog and manual-entry branches, not calculation logic.
* Reports are A4 portrait only.
* Grade scales are configurable placeholders, explicitly not an official SEBA
  grading table.
* The packaged build is one-folder and about 298 MB because Qt, matplotlib and
  pandas are bundled; this is expected for PyInstaller.
* The app is single-teacher and single-machine by design (no multi-user login or
  network sync).
* Tests were run on this Windows machine only; macOS/Linux were not verified.
