"""Backup page: create, validate, list and restore local database backups."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app import config
from app.context import AppContext
from app.database import DatabaseError
from app.ui.icons import make_icon
from app.ui.widgets import (
    DataTable,
    PageHeader,
    StatCard,
    busy,
    confirm_action,
    error_dialog,
    format_pct,
    info_dialog,
    notify,
    palette,
    set_variant,
)
from app.utils.validators import ValidationError


class BackupPage(QWidget):
    data_restored = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(12)
        outer.addWidget(
            PageHeader(
                "Backup & restore",
                "Local SQLite backups. Restoring validates the file first and always creates a "
                "safety backup of the current database.",
            )
        )
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("small")
        outer.addWidget(self.subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cards: dict[str, StatCard] = {}
        for key, label, icon, accent in (
            ("backups", "Backups available", "backup", "primary"),
            ("last", "Last backup", "check", "success"),
            ("size", "Database size", "analytics", "info"),
            ("auto", "Automatic backup", "settings", "accent"),
        ):
            card = StatCard(label, "—", "", icon, accent)
            card.setMinimumHeight(100)
            self.cards[key] = card
            cards.addWidget(card, 1)
        outer.addLayout(cards)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 12, 16, 12)
        settings_layout.setSpacing(8)
        title = QLabel("Backup settings")
        title.setObjectName("cardTitle")
        settings_layout.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Backup folder"))
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        row.addWidget(self.folder_edit, 1)
        choose = QPushButton("Choose folder…")
        choose.setIcon(make_icon("folder", palette()["text"], 15))
        choose.clicked.connect(self._choose_folder)
        row.addWidget(choose)
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(self._open_folder)
        row.addWidget(open_folder)
        settings_layout.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("Automatic backup every"))
        self.auto_days = QSpinBox()
        self.auto_days.setRange(0, 365)
        self.auto_days.setSuffix(" days")
        self.auto_days.setSpecialValueText("Disabled")
        row2.addWidget(self.auto_days)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Keep the latest"))
        self.retention = QSpinBox()
        self.retention.setRange(1, 200)
        self.retention.setSuffix(" backups")
        row2.addWidget(self.retention)
        row2.addStretch(1)
        save = QPushButton("Save backup settings")
        save.setIcon(make_icon("check", "#ffffff", 15))
        set_variant(save, "primary")
        save.clicked.connect(self._save_settings)
        row2.addWidget(save)
        settings_layout.addLayout(row2)
        note = QLabel(
            "Automatic backups are created when the app starts and a backup is due. Backups are "
            "SQLite copies validated with an integrity check before use."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        settings_layout.addWidget(note)
        outer.addWidget(settings_card)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        backup_now = QPushButton("Back up now")
        backup_now.setIcon(make_icon("backup", "#ffffff", 15))
        set_variant(backup_now, "primary")
        backup_now.clicked.connect(self._backup_now)
        actions.addWidget(backup_now)
        restore = QPushButton("Restore selected")
        restore.setIcon(make_icon("import", palette()["text"], 15))
        restore.clicked.connect(self._restore_selected)
        actions.addWidget(restore)
        from_file = QPushButton("Restore from file…")
        from_file.clicked.connect(self._restore_file)
        actions.addWidget(from_file)
        validate = QPushButton("Validate selected")
        validate.clicked.connect(self._validate_selected)
        actions.addWidget(validate)
        actions.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.setIcon(make_icon("refresh", palette()["text"], 15))
        refresh.clicked.connect(self.refresh)
        actions.addWidget(refresh)
        outer.addLayout(actions)

        self.table = DataTable(["Backup file", "Modified", "Size", "Type"])
        self.table.apply_widths([330, 150, 100, 120])
        self.table.itemSelectionChanged.connect(self._selection_changed)
        outer.addWidget(self.table, 1)
        self.detail = QLabel("Select a backup to validate it.")
        self.detail.setObjectName("small")
        self.detail.setWordWrap(True)
        outer.addWidget(self.detail)

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        settings = self.context.settings
        self.subtitle.setText(
            f"Database: {self.context.db.path} · Session {settings.active_session_name()}"
        )
        backups = self.context.backup.list_backups()
        rows = []
        ids = []
        for item in backups:
            kind = "Before restore" if "before_restore" in item["name"] else (
                "Automatic" if "auto" in item["name"] else "Manual"
            )
            rows.append(
                [
                    item["name"],
                    item["modified"],
                    self._human_size(item["size"]),
                    kind,
                ]
            )
            ids.append(str(item["path"]))
        self.table.set_data(rows, row_ids=ids)
        self.cards["backups"].set_value(len(backups), self._folder_text())
        last = settings.get("last_backup_at", "")
        self.cards["last"].set_value(
            last.replace("T", " ")[:16] if last else "Never",
            "Automatic or manual",
        )
        db_size = self.context.db.path.stat().st_size if self.context.db.path.exists() else 0
        self.cards["size"].set_value(self._human_size(db_size), "SQLite database file")
        days = settings.auto_backup_days
        self.cards["auto"].set_value(
            f"Every {days} days" if days > 0 else "Disabled",
            f"Keep latest {settings.backup_retention}",
        )
        self.folder_edit.setText(str(self.context.backup.backup_dir()))
        self.auto_days.setValue(days)
        self.retention.setValue(settings.backup_retention)
        if self.table.rowCount() == 0:
            self.detail.setText(
                "No backups yet. Choose “Back up now” to create the first validated backup."
            )

    @staticmethod
    def _human_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} GB"

    def _folder_text(self) -> str:
        """Short, single-line version of the backup path for the stat card."""
        text = str(self.context.backup.backup_dir())
        if len(text) <= 42:
            return text
        from pathlib import Path

        parts = Path(text).parts
        if len(parts) >= 3:
            return f"{parts[0]}…{parts[-2]}\\{parts[-1]}"
        return "…" + text[-38:]

    # ---------------------------------------------------------------- settings
    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose backup folder", str(self.context.backup.backup_dir())
        )
        if not path:
            return
        try:
            self.context.backup.set_backup_dir(path)
        except (OSError, DatabaseError) as exc:
            error_dialog(self, "Could not set backup folder", str(exc))
            return
        self.refresh()
        notify(self, "Backup folder updated.")

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.backup.backup_dir())))

    def _save_settings(self) -> None:
        self.context.settings.set_many(
            {
                "auto_backup_days": self.auto_days.value(),
                "backup_retention": max(1, self.retention.value()),
            }
        )
        self.context.backup.prune_backups()
        self.refresh()
        notify(self, "Backup settings saved.")

    # ----------------------------------------------------------------- actions
    def _backup_now(self) -> None:
        try:
            with busy(self):
                path = self.context.backup.create_backup("manual")
        except (ValidationError, DatabaseError, OSError) as exc:
            error_dialog(self, "Backup failed", str(exc))
            return
        self.refresh()
        notify(self, f"Backup created: {Path(path).name}")

    def _selected_path(self) -> str | None:
        return self.table.selected_row_id()

    def _selection_changed(self) -> None:
        path = self._selected_path()
        if not path:
            return
        info = self.context.backup.validate_backup_file(path)
        if info["valid"]:
            counts = info.get("counts", {})
            self.detail.setText(
                f"{Path(path).name}: VALID · schema v{info.get('schema_version', '?')} · "
                f"{counts.get('students', 0)} students · {counts.get('attendance', 0)} attendance "
                f"records · {counts.get('examinations', 0)} examinations · "
                f"{counts.get('marks', 0)} marks. {info.get('message_extra', '')}"
            )
        else:
            self.detail.setText(f"{Path(path).name}: INVALID · {info['message']}")

    def _validate_selected(self) -> None:
        path = self._selected_path()
        if not path:
            info_dialog(self, "No backup selected", "Select a backup row first.")
            return
        info = self.context.backup.validate_backup_file(path)
        self._selection_changed()
        if info["valid"]:
            info_dialog(self, "Backup is valid", info["message"] + "\n\n" + info.get("message_extra", ""))
        else:
            error_dialog(self, "Backup is not valid", info["message"])

    def _restore_selected(self) -> None:
        path = self._selected_path()
        if not path:
            info_dialog(self, "No backup selected", "Select a backup row first.")
            return
        self._restore(path)

    def _restore_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a School Manager backup",
            str(self.context.backup.backup_dir()),
            "SQLite backup (*.db);;All files (*.*)",
        )
        if path:
            self._restore(path)

    def _restore(self, path: str) -> None:
        info = self.context.backup.validate_backup_file(path)
        if not info["valid"]:
            error_dialog(self, "Backup is not valid", info["message"])
            return
        counts = info.get("counts", {})
        if not confirm_action(
            self,
            "Restore backup",
            f"Replace the current database with {Path(path).name}?\n\n"
            f"The backup contains {counts.get('students', 0)} students, "
            f"{counts.get('attendance', 0)} attendance records and "
            f"{counts.get('marks', 0)} marks. A safety backup of the current database will be "
            "created first.",
            confirm_text="Restore backup",
            danger=True,
        ):
            return
        try:
            with busy(self):
                result = self.context.backup.restore_backup(path)
        except (ValidationError, DatabaseError, OSError) as exc:
            error_dialog(self, "Restore failed", str(exc))
            return
        self.context.settings.reload()
        self.refresh()
        self.data_restored.emit()
        notify(
            self,
            f"Backup restored. Safety copy: {Path(result['safety_backup']).name}",
            "info",
            5000,
        )
