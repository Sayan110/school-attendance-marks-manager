"""Entry point for the School Attendance & Marks Manager desktop application.

Run the app:            python main.py
Capture offscreen UI:   python main.py --screenshots C:\\temp\\shots
Smoke test (no window):  python main.py --smoke-test
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import traceback
from pathlib import Path

# Keep matplotlib on the Qt backend before any chart module imports pyplot.
os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("MPLBACKEND", "QtAgg")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="SchoolAttendanceManager",
        description="School Attendance & Marks Manager — offline desktop app.",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="build every page against a temporary database, then exit",
    )
    parser.add_argument(
        "--screenshots",
        metavar="DIR",
        help="render every page offscreen into DIR as PNG files, then exit",
    )
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        help="override the writable data directory (used by tests and demos)",
    )
    parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="skip the single-instance check and start a second copy",
    )
    return parser.parse_args(argv)


def _prepare_environment(args: argparse.Namespace, temp_dirs: list[tempfile.TemporaryDirectory]) -> None:
    """Apply headless overrides and isolated storage before Qt or the DB start."""
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    elif args.screenshots:
        # Screenshots use the real platform so Windows fonts render, but the
        # window is moved off-screen before it is captured.
        os.environ.pop("QT_QPA_PLATFORM", None)
    else:
        os.environ.pop("QT_QPA_PLATFORM", None)

    if args.data_dir:
        os.environ["SVSM_DATA_DIR"] = str(Path(args.data_dir).expanduser().resolve())
        os.environ.pop("SVSM_DB_PATH", None)
    elif (args.smoke_test or args.screenshots) and not os.environ.get("SVSM_DATA_DIR"):
        # Never touch the teacher's real database while smoke-testing.
        holder = tempfile.TemporaryDirectory(prefix="svsm-smoke-")
        temp_dirs.append(holder)
        os.environ["SVSM_DATA_DIR"] = holder.name
        os.environ.pop("SVSM_DB_PATH", None)


def _install_excepthook() -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app import config

    def handler(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            logs = config.ensure_data_dirs()["logs"]
            with (logs / "crash.log").open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except Exception:
            pass
        sys.__stderr__.write(text)
        app = QApplication.instance()
        if app is not None and app.platformName() != "offscreen":
            QMessageBox.critical(
                None,
                "Unexpected error",
                "Something went wrong. The details were written to the log folder.\n\n"
                f"{exc_value}",
            )

    sys.excepthook = handler


def _capture_pages(window, target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    from PySide6.QtWidgets import QApplication

    for key in list(window.pages.keys()):
        window.navigate_to(key)
        QApplication.processEvents()
        app = QApplication.instance()
        if app is not None:
            for _ in range(3):
                app.processEvents()
        pixmap = window.grab()
        path = target / f"{key}.png"
        pixmap.save(str(path), "PNG")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    from app import config

    if args.version:
        print(f"{config.APP_NAME} {config.VERSION}")
        return 0

    temp_dirs: list[tempfile.TemporaryDirectory] = []
    _prepare_environment(args, temp_dirs)

    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from app.context import AppContext
        from app.ui import widgets as widget_module
        from app.ui.icons import school_logo
        from app.ui.main_window import MainWindow
        from app.ui.theme import apply_theme
        from app.ui.widgets import set_palette
        from app.utils.single_instance import SingleInstance

        _install_excepthook()

        config.ensure_data_dirs()
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
        app = QApplication(sys.argv[:1])
        app.setApplicationName(config.APP_NAME)
        app.setApplicationDisplayName(config.APP_NAME)
        app.setOrganizationName(config.ORG_NAME)
        app.setDesktopFileName("SchoolAttendanceManager")

        icon_file = config.icon_path()
        app.setWindowIcon(QIcon(str(icon_file)) if icon_file.exists() else QIcon(school_logo(64)))

        holder: dict[str, MainWindow] = {}
        single: SingleInstance | None = None
        headless = args.smoke_test or args.screenshots

        if not headless and not args.allow_multiple:
            single = SingleInstance()
            if not single.start_server():
                single.close()
                print("School Attendance & Marks Manager is already running.")
                return 0

        context = AppContext()
        context.settings.reload()

        palette_dict = apply_theme(app, context.settings.theme)
        set_palette(palette_dict)
        widget_module.set_palette(palette_dict)

        window = MainWindow(context)
        holder["window"] = window

        def activate() -> None:
            current = holder.get("window")
            if current is None:
                return
            current.showNormal()
            current.raise_()
            current.activateWindow()

        if single is not None:
            single._on_activate = activate

        try:
            context.backup.auto_backup_if_due()
        except Exception:
            pass

        if headless:
            if args.screenshots:
                window.move(-6000, -6000)
            window.show()
            app.processEvents()
            if args.screenshots:
                written = _capture_pages(window, Path(args.screenshots).expanduser())
                for path in written:
                    print(f"screenshot: {path}")
            else:
                for key in window.pages:
                    window.navigate_to(key)
                    app.processEvents()
                print("smoke-test: all pages built and refreshed")
            window._closing = True
            window._save_geometry()
            context.close()
            from app.ui.shutdown import shutdown_qt

            shutdown_qt(app)
            print("smoke-test: OK")
            return 0

        window.show()
        exit_code = app.exec()
        if single is not None:
            single.close()
        from app.ui.shutdown import shutdown_qt

        shutdown_qt(app)
        return int(exit_code)
    finally:
        for holder_dir in temp_dirs:
            try:
                holder_dir.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
