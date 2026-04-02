"""Request Log Analysis dialog.

Shows a multi-select list of all skills. User picks which skills are involved,
clicks OK, and the dialog zips everything up and uploads to S3 for support analysis.
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QProgressBar, QMessageBox, QAbstractItemView,
)

from gui.messages import get_message
from utils.logger_helper import logger_helper as logger


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _UploadWorker(QThread):
    finished = Signal(str)   # success message
    error = Signal(str)      # error message

    def __init__(self, skill_ids: List[str]):
        super().__init__()
        self._skill_ids = skill_ids

    def run(self):
        try:
            from gui.ipc.w2p_handlers.debug_log_handler import perform_log_analysis_upload
            message = perform_log_analysis_upload(self._skill_ids)
            self.finished.emit(message)
        except Exception as exc:
            logger.error(f"[RequestLogAnalysis] Upload failed: {exc}", exc_info=True)
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class RequestLogAnalysisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(get_message("request_log_analysis") or "Request Log Analysis")
        self.setFixedSize(520, 520)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._worker: _UploadWorker | None = None
        self._setup_ui()
        self._apply_styles()
        self._load_skills()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Description
        desc = QLabel("Select the skills involved in this debug session.\n"
                      "The skill files, referenced prompts, and eCan.log will be\n"
                      "packaged and uploaded to the support team.")
        desc.setWordWrap(True)
        desc.setObjectName("descLabel")
        layout.addWidget(desc)

        # Skill list
        self._skill_list = QListWidget()
        self._skill_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self._skill_list.setObjectName("skillList")
        layout.addWidget(self._skill_list, stretch=1)

        # Select-all / deselect-all row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        btn_all = QPushButton("Select All")
        btn_all.setObjectName("secondaryBtn")
        btn_all.setFixedHeight(28)
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("Deselect All")
        btn_none.setObjectName("secondaryBtn")
        btn_none.setFixedHeight(28)
        btn_none.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Progress area (hidden until upload starts)
        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(6)
        self._progress.hide()
        layout.addWidget(self._progress)

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setObjectName("primaryBtn")
        self._ok_btn.setFixedWidth(100)
        self._ok_btn.setFixedHeight(32)
        self._ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply_styles(self):
        self.setStyleSheet("""
        QDialog {
            background-color: #1e2936;
        }
        QLabel {
            color: #e6edf3;
            font-size: 13px;
        }
        QLabel#descLabel {
            color: #c9d1d9;
            font-size: 13px;
            line-height: 1.5;
        }
        QLabel#statusLabel {
            color: #8b949e;
            font-size: 12px;
        }
        QListWidget#skillList {
            background-color: #161b22;
            color: #e6edf3;
            border: 1px solid #30363d;
            border-radius: 6px;
            font-size: 13px;
            padding: 4px;
        }
        QListWidget#skillList::item {
            padding: 6px 8px;
            border-radius: 4px;
        }
        QListWidget#skillList::item:selected {
            background-color: #1f6feb;
            color: white;
        }
        QListWidget#skillList::item:hover:!selected {
            background-color: #21262d;
        }
        QPushButton#primaryBtn {
            background-color: #238636;
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton#primaryBtn:hover { background-color: #2ea043; }
        QPushButton#primaryBtn:pressed { background-color: #1a7f37; }
        QPushButton#primaryBtn:disabled { background-color: #3d4448; color: #6e7681; }
        QPushButton#secondaryBtn {
            background-color: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            border-radius: 6px;
            font-size: 12px;
        }
        QPushButton#secondaryBtn:hover { background-color: #30363d; }
        QPushButton#secondaryBtn:pressed { background-color: #161b22; }
        QProgressBar {
            background-color: #21262d;
            border: none;
            border-radius: 3px;
        }
        QProgressBar::chunk {
            background-color: #1f6feb;
            border-radius: 3px;
        }
        """)

    # ------------------------------------------------------------------
    # Skill loading
    # ------------------------------------------------------------------

    def _load_skills(self):
        """Populate the skill list from agent_skills in memory."""
        self._skill_list.clear()
        skills = self._get_skills()
        if not skills:
            item = QListWidgetItem("(No skills found)")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self._skill_list.addItem(item)
            return
        for sid, name in skills:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, sid)
            self._skill_list.addItem(item)

    def _get_skills(self) -> list[tuple[str, str]]:
        """Return list of (skill_id, skill_name) tuples."""
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            if mainwin:
                agent_skills = getattr(mainwin, "agent_skills", None) or []
                if agent_skills:
                    return [
                        (str(getattr(sk, "id", "") or ""), str(getattr(sk, "name", "") or ""))
                        for sk in agent_skills
                        if getattr(sk, "id", None) and getattr(sk, "name", None)
                    ]
        except Exception as exc:
            logger.warning(f"[RequestLogAnalysis] Could not load skills from memory: {exc}")

        # Fallback: scan my_skills directory
        try:
            from utils.user_path_helper import get_user_data_dir
            import json
            from pathlib import Path
            skills_dir = Path(get_user_data_dir(subdir="my_skills"))
            result = []
            if skills_dir.is_dir():
                for skill_dir in skills_dir.iterdir():
                    if not skill_dir.is_dir():
                        continue
                    for json_file in (skill_dir / "diagram_dir").glob("*.json") if (skill_dir / "diagram_dir").is_dir() else []:
                        try:
                            data = json.loads(json_file.read_text(encoding="utf-8"))
                            sid = str(data.get("skillId") or data.get("id") or "")
                            name = str(data.get("name") or data.get("title") or skill_dir.name)
                            if sid:
                                result.append((sid, name))
                                break
                        except Exception:
                            continue
            return result
        except Exception as exc:
            logger.warning(f"[RequestLogAnalysis] Skill dir scan failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _select_all(self):
        for i in range(self._skill_list.count()):
            self._skill_list.item(i).setSelected(True)

    def _deselect_all(self):
        self._skill_list.clearSelection()

    def _on_ok(self):
        selected = [
            item.data(Qt.UserRole)
            for item in self._skill_list.selectedItems()
            if item.data(Qt.UserRole)
        ]
        # Allow upload with no skills — the log file alone is useful for support.
        self._start_upload(selected)

    def _start_upload(self, skill_ids: List[str]):
        self._ok_btn.setEnabled(False)
        self._status_label.setText("Packaging and uploading debug log…")
        self._status_label.show()
        self._progress.show()

        self._worker = _UploadWorker(skill_ids)
        self._worker.finished.connect(self._on_upload_done)
        self._worker.error.connect(self._on_upload_error)
        self._worker.start()

    def _on_upload_done(self, message: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        QMessageBox.information(self, "Upload Complete", message or "Debug package uploaded successfully.")
        self.accept()

    def _on_upload_error(self, error: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        QMessageBox.critical(self, "Upload Failed",
                             f"Failed to upload debug package:\n\n{error}")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)
