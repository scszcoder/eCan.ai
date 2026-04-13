"""SQLite Merge dialog.

Lets the user pick a source (old) and target (new) SQLite database file,
then merges rows from the source into the target — inserting into empty
tables and skipping tables that already have data.
"""
from __future__ import annotations

import os
import sqlite3
from typing import List, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QProgressBar,
)

from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Merge logic (runs in background thread)
# ---------------------------------------------------------------------------

class _MergeWorker(QThread):
    progress = Signal(str)          # log line
    finished = Signal(str)          # final summary
    error = Signal(str)             # error message

    def __init__(self, old_path: str, new_path: str):
        super().__init__()
        self._old_path = old_path
        self._new_path = new_path

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _get_tables_with_counts(conn: sqlite3.Connection) -> dict[str, int]:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        return {t: conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] for t in tables}

    @staticmethod
    def _get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
        return [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]

    # ---- main --------------------------------------------------------------

    def run(self):  # noqa: C901 – sequential merge logic, fine as-is
        try:
            old_path, new_path = self._old_path, self._new_path

            self.progress.emit(f"Source DB: {old_path}")
            self.progress.emit(f"Target DB: {new_path}")
            self.progress.emit("")

            conn_old = sqlite3.connect(old_path)
            conn_new = sqlite3.connect(new_path)
            conn_new.execute("PRAGMA journal_mode=WAL")
            conn_new.execute("PRAGMA busy_timeout=5000")

            old_counts = self._get_tables_with_counts(conn_old)
            new_counts = self._get_tables_with_counts(conn_new)

            # Skip meta tables
            skip_tables = {"db_version", "migration_logs", "sqlite_sequence"}

            tables_to_port: List[Tuple[str, int]] = []
            for table, old_count in sorted(old_counts.items()):
                if old_count == 0:
                    continue
                if table in skip_tables:
                    self.progress.emit(f"  SKIP  {table} ({old_count} rows) — meta table")
                    continue
                if table not in new_counts:
                    self.progress.emit(f"  SKIP  {table} ({old_count} rows) — not in target DB")
                    continue
                new_count = new_counts[table]
                if new_count > 0:
                    self.progress.emit(
                        f"  SKIP  {table} (old={old_count}, new={new_count}) — target not empty"
                    )
                    continue
                tables_to_port.append((table, old_count))

            self.progress.emit("")
            if not tables_to_port:
                self.finished.emit("Nothing to merge — all target tables already have data or source is empty.")
                conn_old.close()
                conn_new.close()
                return

            self.progress.emit(
                f"Will merge {len(tables_to_port)} table(s): "
                + ", ".join(f"{t}({c})" for t, c in tables_to_port)
            )
            self.progress.emit("")

            total_rows = 0
            for table, old_count in tables_to_port:
                new_cols = self._get_columns(conn_new, table)
                old_cols = self._get_columns(conn_old, table)
                common_cols = [c for c in new_cols if c in old_cols]

                cols_str = ", ".join(f"[{c}]" for c in common_cols)
                rows = conn_old.execute(f"SELECT {cols_str} FROM [{table}]").fetchall()
                if not rows:
                    self.progress.emit(f"  {table}: 0 rows (skip)")
                    continue

                placeholders = ", ".join(["?"] * len(common_cols))
                insert_sql = f"INSERT OR IGNORE INTO [{table}] ({cols_str}) VALUES ({placeholders})"
                conn_new.executemany(insert_sql, rows)
                conn_new.commit()

                after = conn_new.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]

                dropped_cols = set(old_cols) - set(new_cols)
                extra = ""
                if dropped_cols:
                    extra = f"  (dropped cols: {sorted(dropped_cols)})"
                self.progress.emit(f"  OK    {table}: {len(rows)} rows inserted (verified: {after}){extra}")
                total_rows += len(rows)

            conn_old.close()
            conn_new.close()

            self.finished.emit(
                f"Merge complete: {total_rows} rows across {len(tables_to_port)} tables."
            )

        except Exception as exc:
            logger.error(f"[SQLiteMerge] Merge failed: {exc}", exc_info=True)
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SQLiteMergeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SQLite Merge")
        self.setMinimumSize(620, 480)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._worker: _MergeWorker | None = None
        self._setup_ui()
        self._apply_styles()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        desc = QLabel(
            "Merge rows from a source (old) SQLite database into a target (new) database.\n"
            "Only empty tables in the target will be filled; tables with existing data are skipped.\n"
            "A backup of the target is created automatically before merging."
        )
        desc.setWordWrap(True)
        desc.setObjectName("descLabel")
        layout.addWidget(desc)

        # --- Source DB ---
        src_label = QLabel("Source DB (old):")
        src_label.setObjectName("fieldLabel")
        layout.addWidget(src_label)

        src_row = QHBoxLayout()
        self._src_input = QLineEdit()
        self._src_input.setPlaceholderText("Path to source .db file")
        src_row.addWidget(self._src_input, stretch=1)
        src_browse = QPushButton("...")
        src_browse.setFixedWidth(36)
        src_browse.setToolTip("Browse for source database file")
        src_browse.clicked.connect(lambda: self._browse("src"))
        src_row.addWidget(src_browse)
        layout.addLayout(src_row)

        # --- Target DB ---
        tgt_label = QLabel("Target DB (new):")
        tgt_label.setObjectName("fieldLabel")
        layout.addWidget(tgt_label)

        tgt_row = QHBoxLayout()
        self._tgt_input = QLineEdit()
        self._tgt_input.setPlaceholderText("Path to target .db file")
        tgt_row.addWidget(self._tgt_input, stretch=1)
        tgt_browse = QPushButton("...")
        tgt_browse.setFixedWidth(36)
        tgt_browse.setToolTip("Browse for target database file")
        tgt_browse.clicked.connect(lambda: self._browse("tgt"))
        tgt_row.addWidget(tgt_browse)
        layout.addLayout(tgt_row)

        # --- Log output ---
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("logOutput")
        layout.addWidget(self._log, stretch=1)

        # --- Progress bar ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._merge_btn = QPushButton("Merge")
        self._merge_btn.setFixedWidth(120)
        self._merge_btn.setObjectName("mergeBtn")
        self._merge_btn.clicked.connect(self._on_merge)
        btn_row.addWidget(self._merge_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedWidth(120)
        self._close_btn.clicked.connect(self.close)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog { background: #1e1e2e; color: #cdd6f4; }
            QLabel#descLabel { color: #a6adc8; font-size: 13px; margin-bottom: 4px; }
            QLabel#fieldLabel { color: #cdd6f4; font-weight: bold; font-size: 13px; }
            QLineEdit {
                background: #313244; color: #cdd6f4; border: 1px solid #45475a;
                border-radius: 4px; padding: 6px 8px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #89b4fa; }
            QPushButton {
                background: #45475a; color: #cdd6f4; border: 1px solid #585b70;
                border-radius: 4px; padding: 6px 12px; font-size: 13px;
            }
            QPushButton:hover { background: #585b70; }
            QPushButton#mergeBtn { background: #89b4fa; color: #1e1e2e; font-weight: bold; }
            QPushButton#mergeBtn:hover { background: #74c7ec; }
            QPushButton#mergeBtn:disabled { background: #45475a; color: #6c7086; }
            QTextEdit#logOutput {
                background: #11111b; color: #a6e3a1; border: 1px solid #45475a;
                border-radius: 4px; font-family: Consolas, monospace; font-size: 12px;
                padding: 8px;
            }
            QProgressBar {
                background: #313244; border: 1px solid #45475a; border-radius: 4px;
                height: 6px;
            }
            QProgressBar::chunk { background: #89b4fa; border-radius: 3px; }
        """)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _browse(self, which: str):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite Database", "",
            "SQLite files (*.db *.sqlite *.sqlite3);;All files (*)"
        )
        if path:
            if which == "src":
                self._src_input.setText(path)
            else:
                self._tgt_input.setText(path)

    def _on_merge(self):
        old_path = self._src_input.text().strip()
        new_path = self._tgt_input.text().strip()

        if not old_path or not new_path:
            QMessageBox.warning(self, "Missing Input", "Please select both source and target database files.")
            return
        if not os.path.isfile(old_path):
            QMessageBox.warning(self, "File Not Found", f"Source file not found:\n{old_path}")
            return
        if not os.path.isfile(new_path):
            QMessageBox.warning(self, "File Not Found", f"Target file not found:\n{new_path}")
            return
        if os.path.abspath(old_path) == os.path.abspath(new_path):
            QMessageBox.warning(self, "Same File", "Source and target must be different files.")
            return

        # Backup target
        backup_path = new_path + ".bak_before_merge"
        try:
            import shutil
            shutil.copy2(new_path, backup_path)
            self._log.append(f"Backup created: {backup_path}\n")
        except Exception as e:
            QMessageBox.warning(self, "Backup Failed", f"Could not back up target:\n{e}")
            return

        self._merge_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._log.clear()
        self._log.append(f"Backup created: {backup_path}\n")

        self._worker = _MergeWorker(old_path, new_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, line: str):
        self._log.append(line)

    def _on_finished(self, summary: str):
        self._progress.setVisible(False)
        self._merge_btn.setEnabled(True)
        self._log.append(f"\n{summary}")
        logger.info(f"[SQLiteMerge] {summary}")

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._merge_btn.setEnabled(True)
        self._log.append(f"\nERROR: {msg}")
        QMessageBox.critical(self, "Merge Failed", f"Merge failed:\n{msg}")
