"""Main window: sidebar navigation, topbar, page lifecycle and theme handling."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.context import AppContext
from app.ui import widgets as widget_module
from app.ui.attendance import AttendancePage
from app.ui.analytics import AnalyticsPage
from app.ui.backup import BackupPage
from app.ui.dashboard import DashboardPage
from app.ui.icons import make_icon, school_logo
from app.ui.marks import MarksPage
from app.ui.reports_page import ReportsPage
from app.ui.settings_page import SettingsPage
from app.ui.students import StudentsPage
from app.ui.theme import apply_theme
from app.ui.widgets import confirm_action, notify, polish_inputs, set_palette


NAV_SECTIONS = [
    (
        "OVERVIEW",
        [
            ("dashboard", "Dashboard", "dashboard"),
        ],
    ),
    (
        "MANAGE",
        [
            ("students", "Students", "students"),
            ("attendance", "Attendance", "attendance"),
            ("marks", "Marks & exams", "marks"),
        ],
    ),
    (
        "INSIGHTS",
        [
            ("analytics", "Analytics", "analytics"),
            ("reports", "Reports", "reports"),
        ],
    ),
    (
        "SYSTEM",
        [
            ("backup", "Backup", "backup"),
            ("settings", "Settings", "settings"),
        ],
    ),
]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self._current_key = "dashboard"
        self._loading_session = False
        self._closing = False
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumSize(1120, 720)
        self.resize(1380, 880)
        self.setWindowIcon(self._window_icon())
        self._build_menu()
        self._build_ui()
        self._restore_geometry()
        self.navigate_to("dashboard")

    # ------------------------------------------------------------------- build
    def _window_icon(self) -> QIcon:
        path = config.icon_path()
        if path.exists():
            return QIcon(str(path))
        return QIcon(school_logo(64))

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        refresh = QAction("Refresh current page", self)
        refresh.setShortcut(QKeySequence("F5"))
        refresh.triggered.connect(self.refresh_current)
        file_menu.addAction(refresh)
        file_menu.addSeparator()
        backup = QAction("Back up database now", self)
        backup.triggered.connect(self._quick_backup)
        file_menu.addAction(backup)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)
        rules = QAction("Attendance and marks rules", self)
        rules.triggered.connect(self._rules_help)
        help_menu.addAction(rules)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(236)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(14, 16, 14, 14)
        side.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(school_logo(38))
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("School Manager")
        title.setObjectName("brandTitle")
        brand_text.addWidget(title)
        school = QLabel(config.SCHOOL_NAME)
        school.setObjectName("brandSchool")
        school.setWordWrap(True)
        brand_text.addWidget(school)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(10)

        self.nav_buttons: dict[str, QPushButton] = {}
        for section, items in NAV_SECTIONS:
            label = QLabel(section)
            label.setObjectName("sidebarSection")
            side.addWidget(label)
            for key, text, icon in items:
                button = QPushButton(text.replace("&", "&&"))
                button.setObjectName("navButton")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setIcon(make_icon(icon, config.THEME_LIGHT["sidebar_text"], 18))
                button.setIconSize(QSize(18, 18))
                button.setMinimumHeight(36)
                button.clicked.connect(lambda _=False, k=key: self.navigate_to(k))
                self.nav_buttons[key] = button
                side.addWidget(button)
            side.addSpacing(4)
        side.addStretch(1)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setStyleSheet(f"background: {config.THEME_LIGHT['sidebar_hover']};")
        side.addWidget(divider)
        self.sidebar_hint = QLabel("All data stays on this computer.")
        self.sidebar_hint.setObjectName("sidebarFooter")
        self.sidebar_hint.setWordWrap(True)
        side.addWidget(self.sidebar_hint)
        version = QLabel(f"Version {config.VERSION}")
        version.setObjectName("sidebarFooter")
        side.addWidget(version)
        root.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(58)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(22, 8, 18, 8)
        top_layout.setSpacing(10)
        self.breadcrumb = QLabel("Dashboard")
        self.breadcrumb.setObjectName("pageSubtitle")
        self.breadcrumb.setStyleSheet("font-weight: 600;")
        top_layout.addWidget(self.breadcrumb)
        top_layout.addStretch(1)
        top_layout.addWidget(QLabel("Academic session"))
        self.session_combo = QComboBox()
        self.session_combo.setMinimumWidth(132)
        self.session_combo.currentIndexChanged.connect(self._session_combo_changed)
        top_layout.addWidget(self.session_combo)
        self.teacher_label = QLabel("")
        self.teacher_label.setObjectName("small")
        top_layout.addWidget(self.teacher_label)
        self.theme_button = QPushButton()
        self.theme_button.setFixedSize(32, 32)
        self.theme_button.setToolTip("Switch light/dark theme")
        self.theme_button.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_button)
        right.addWidget(topbar)

        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        root.addLayout(right, 1)
        self.setCentralWidget(central)

        self.pages: dict[str, QWidget] = {}
        self.page_indices: dict[str, int] = {}
        self._create_pages()
        self._refresh_session_combo()
        self._update_chrome()

    def _create_pages(self) -> None:
        while self.stack.count():
            page = self.stack.widget(0)
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages = {
            "dashboard": DashboardPage(self.context),
            "students": StudentsPage(self.context),
            "attendance": AttendancePage(self.context),
            "marks": MarksPage(self.context),
            "analytics": AnalyticsPage(self.context),
            "reports": ReportsPage(self.context),
            "backup": BackupPage(self.context),
            "settings": SettingsPage(self.context),
        }
        self.page_indices = {}
        for key, page in self.pages.items():
            self.page_indices[key] = self.stack.addWidget(page)
        polish_inputs(self)
        self._wire_pages()

    def _wire_pages(self) -> None:
        dashboard = self.pages["dashboard"]
        dashboard.navigate.connect(self.navigate_to)
        dashboard.session_change_requested.connect(self.change_session)
        for key in ("attendance", "marks"):
            page = self.pages[key]
            if hasattr(page, "navigate"):
                page.navigate.connect(self.navigate_to)
        settings = self.pages["settings"]
        settings.theme_changed.connect(self.apply_theme)
        settings.session_changed.connect(self.change_session)
        settings.settings_saved.connect(self.refresh_all)
        self.pages["backup"].data_restored.connect(self._after_restore)

    # ------------------------------------------------------------------- chrome
    def _refresh_session_combo(self) -> None:
        self._loading_session = True
        try:
            current = self.context.session_id
            self.session_combo.clear()
            for session in self.context.settings.sessions():
                self.session_combo.addItem(str(session["name"]), int(session["id"]))
            index = self.session_combo.findData(current)
            if index >= 0:
                self.session_combo.setCurrentIndex(index)
        finally:
            self._loading_session = False

    def _update_chrome(self) -> None:
        theme = self.context.settings.theme
        self.theme_button.setIcon(
            make_icon("sun" if theme == "dark" else "moon", config.theme_palette(theme)["text"], 17)
        )
        self.theme_button.setStyleSheet("")
        teacher = self.context.settings.teacher_name
        self.teacher_label.setText(teacher if teacher else "")
        self.teacher_label.setVisible(bool(teacher))
        for key, button in self.nav_buttons.items():
            button.setIcon(
                make_icon(
                    dict((k, i) for _, items in NAV_SECTIONS for k, _, i in items)[key],
                    config.theme_palette(theme)["sidebar_text"],
                    18,
                )
            )
        self.breadcrumb.setText(
            dict((k, t) for _, items in NAV_SECTIONS for k, t, _ in items).get(
                self._current_key, "Dashboard"
            )
        )

    # --------------------------------------------------------------- navigation
    def navigate_to(self, key: str) -> None:
        if key not in self.pages:
            return
        if key != self._current_key:
            current = self.pages.get(self._current_key)
            if current is not None and hasattr(current, "has_unsaved_changes"):
                if current.has_unsaved_changes() and not current.confirm_discard(self):
                    self._sync_nav_checks()
                    return
        self._current_key = key
        self.stack.setCurrentIndex(self.page_indices[key])
        self._sync_nav_checks()
        self.breadcrumb.setText(
            dict((k, t) for _, items in NAV_SECTIONS for k, t, _ in items).get(key, key.title())
        )
        page = self.pages[key]
        if hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception as exc:  # pragma: no cover - defensive UI guard
                QMessageBox.warning(self, "Could not refresh page", str(exc))

    def _sync_nav_checks(self) -> None:
        for key, button in self.nav_buttons.items():
            button.setChecked(key == self._current_key)

    def refresh_current(self) -> None:
        self.navigate_to(self._current_key)

    def refresh_all(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:
                    continue
        self._refresh_session_combo()
        self._update_chrome()

    # ----------------------------------------------------------------- session
    def _session_combo_changed(self) -> None:
        if self._loading_session:
            return
        session_id = self.session_combo.currentData()
        if session_id:
            self.change_session(int(session_id))

    def change_session(self, session_id: int) -> None:
        if session_id == self.context.session_id:
            self._refresh_session_combo()
            return
        current = self.pages.get(self._current_key)
        if current is not None and hasattr(current, "has_unsaved_changes"):
            if current.has_unsaved_changes() and not current.confirm_discard(self):
                self._refresh_session_combo()
                return
        try:
            self.context.settings.set_active_session(int(session_id))
        except Exception as exc:
            QMessageBox.warning(self, "Could not switch session", str(exc))
            self._refresh_session_combo()
            return
        self._refresh_session_combo()
        self._update_chrome()
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:
                    continue
        notify(self, f"Active session changed to {self.context.settings.active_session_name()}.", "info")

    # ------------------------------------------------------------------- theme
    def apply_theme(self, name: str) -> None:
        QTimer.singleShot(0, lambda: self._rebuild_for_theme(name))

    def _rebuild_for_theme(self, name: str) -> None:
        app = QApplication.instance()
        if app is None or self._closing:
            return
        palette_dict = apply_theme(app, name)
        set_palette(palette_dict)
        widget_module.set_palette(palette_dict)
        self.context.settings.set("theme", name)
        current = self._current_key
        self._create_pages()
        self._current_key = "dashboard" if current not in self.pages else current
        self.stack.setCurrentIndex(self.page_indices[self._current_key])
        self._sync_nav_checks()
        self._update_chrome()
        self._refresh_session_combo()

    def _toggle_theme(self) -> None:
        new = "dark" if self.context.settings.theme == "light" else "light"
        self.apply_theme(new)

    # ----------------------------------------------------------------- restore
    def _after_restore(self) -> None:
        self.context.settings.reload()
        theme = self.context.settings.theme
        self.apply_theme(theme)

    # ------------------------------------------------------------------ helpers
    def _quick_backup(self) -> None:
        try:
            path = self.context.backup.create_backup("manual")
        except Exception as exc:
            QMessageBox.warning(self, "Backup failed", str(exc))
            return
        notify(self, f"Backup created: {path.name}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {config.APP_NAME}",
            f"<b>{config.APP_NAME}</b><br>Version {config.VERSION}<br><br>"
            f"{config.SCHOOL_NAME}<br>{config.SCHOOL_BOARD}<br>"
            f"Subject: {config.DEFAULT_SUBJECT} · Classes 9 & 10<br><br>"
            "A local, offline desktop application. No internet connection or cloud service is "
            "used. All records stay in the local SQLite database.",
        )

    def _rules_help(self) -> None:
        QMessageBox.information(
            self,
            "Attendance and marks rules",
            "Attendance % = present ÷ counted sessions × 100.\n\n"
            "• Leave sessions are excluded from the denominator when the Settings option is on.\n"
            "• Unmarked sessions are never counted as absences.\n"
            "• Holiday dates are annotated and are not counted in attendance percentages.\n\n"
            "Marks:\n"
            "• Pending, Absent and Exempted are distinct states; a missing mark is never zero.\n"
            "• Pass criteria and grades are configured by the teacher and are not official SEBA "
            "policy.\n"
            "• Ranks use standard competition ranking, so ties share a rank and the next rank "
            "skips.",
        )

    # ----------------------------------------------------------------- geometry
    def _restore_geometry(self) -> None:
        value = self.context.settings.get("window_geometry", "").strip()
        if not value:
            return
        try:
            geometry = QByteArray.fromBase64(value.encode("ascii"))
            if not self.restoreGeometry(geometry):
                return
        except Exception:
            return

    def _save_geometry(self) -> None:
        try:
            data = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.context.settings.set("window_geometry", data)
        except Exception:
            pass

    # -------------------------------------------------------------------- close
    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._closing:
            self._stop_background_timers()
            event.accept()
            return
        dirty_pages = [
            page
            for page in self.pages.values()
            if hasattr(page, "has_unsaved_changes") and page.has_unsaved_changes()
        ]
        if dirty_pages:
            if not confirm_action(
                self,
                "Unsaved changes",
                "Some changes have not been saved. Close the application and discard them?",
                confirm_text="Discard and close",
                danger=True,
            ):
                event.ignore()
                return
        self._closing = True
        self._stop_background_timers()
        self._save_geometry()
        self.context.close()
        event.accept()

    def _stop_background_timers(self) -> None:
        """Stop page timers before the database closes.

        A debounce timer that fires after shutdown would otherwise call a page
        refresh, which reopens the database on a closed context and leaks the
        connection.
        """
        for timer in self.findChildren(QTimer):
            timer.stop()
