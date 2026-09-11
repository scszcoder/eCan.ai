"""Report Bug dialog.

A sequence, not a single submit: the user describes the problem, the description
goes through the server-side intake gate, and only an accepted description gets
packaged and uploaded.

    describe -> [local pre-check] -> validate (server) -> ok? -> confirm -> zip + upload
                                                       -> incomplete? -> ask, revise, retry
                                                       -> rejected? -> stop

The user picks the skills involved and may attach screenshots / a screen
recording; everything (skill files, referenced prompts, the description saved to
current_issues.md, the attachments, and the full runlogs folder) is zipped and
uploaded to support. All strings are localized via ``gui.messages`` (CN
default). The heavy lifting lives in the shared ``debug_log_handler`` so the CLI
(``ecan support upload``) and an agent can do the same thing headlessly.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QProgressBar, QMessageBox, QAbstractItemView, QTextEdit,
    QFileDialog,
)

from gui.messages import get_message
from utils.logger_helper import logger_helper as logger


def _t(key: str, **kwargs) -> str:
    """Localized string, falling back to the key so a missing entry is visible."""
    return get_message(key, **kwargs) or key


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _ValidateWorker(QThread):
    """Runs the server-side intake gate off the UI thread."""

    finished = Signal(dict)  # {status, question, message, grant}
    error = Signal(str)

    def __init__(self, description: str, skill_ids: List[str]):
        super().__init__()
        self._description = description
        self._skill_ids = skill_ids

    def run(self):
        try:
            from gui.ipc.w2p_handlers.debug_log_handler import validate_bug_description
            self.finished.emit(validate_bug_description(self._description, self._skill_ids))
        except Exception as exc:
            logger.error(f"[ReportBug] Description check failed: {exc}", exc_info=True)
            self.error.emit(str(exc))


class _UploadWorker(QThread):
    finished = Signal(str)   # success message
    error = Signal(str)      # error message

    def __init__(self, skill_ids: List[str], description: str = "",
                 attachments: Optional[List[str]] = None,
                 grant: Optional[dict] = None):
        super().__init__()
        self._skill_ids = skill_ids
        self._description = description
        self._attachments = attachments or []
        self._grant = grant or None

    def run(self):
        try:
            from gui.ipc.w2p_handlers.debug_log_handler import perform_log_analysis_upload
            message = perform_log_analysis_upload(
                self._skill_ids, self._description, self._attachments, self._grant)
            self.finished.emit(message)
        except Exception as exc:
            logger.error(f"[ReportBug] Upload failed: {exc}", exc_info=True)
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class RequestLogAnalysisDialog(QDialog):
    # Gate rounds before we stop asking and hand off to support.
    _MAX_GATE_ROUNDS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("request_log_analysis").rstrip(". "))
        self.setMinimumSize(560, 720)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._worker: _UploadWorker | None = None
        self._validator: _ValidateWorker | None = None
        self._attachments: List[str] = []
        # Intake-gate state. The round cap stops an unbounded "still not enough
        # detail" loop (each round costs a server classifier call); the last
        # submitted text stops a resubmit of the same string.
        self._gate_rounds = 0
        self._last_submitted: str | None = None
        self._grant: dict = {}
        self._setup_ui()
        self._apply_styles()
        self._load_skills()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        desc = QLabel(_t("rla_desc"))
        desc.setWordWrap(True)
        desc.setObjectName("descLabel")
        layout.addWidget(desc)

        # Problem description
        layout.addWidget(self._section_label(_t("rla_problem_label")))
        self._problem_edit = QTextEdit()
        self._problem_edit.setObjectName("problemEdit")
        self._problem_edit.setPlaceholderText(_t("rla_problem_placeholder"))
        self._problem_edit.setFixedHeight(90)
        layout.addWidget(self._problem_edit)

        # Skills
        layout.addWidget(self._section_label(_t("rla_skills_label")))
        self._skill_list = QListWidget()
        self._skill_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self._skill_list.setObjectName("skillList")
        layout.addWidget(self._skill_list, stretch=1)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        btn_all = QPushButton(_t("rla_select_all"))
        btn_all.setObjectName("secondaryBtn")
        btn_all.setFixedHeight(28)
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton(_t("rla_deselect_all"))
        btn_none.setObjectName("secondaryBtn")
        btn_none.setFixedHeight(28)
        btn_none.clicked.connect(self._deselect_all)
        sel_row.addWidget(btn_all)
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Attachments
        layout.addWidget(self._section_label(_t("rla_attach_label")))
        self._attach_list = QListWidget()
        self._attach_list.setObjectName("attachList")
        self._attach_list.setFixedHeight(90)
        layout.addWidget(self._attach_list)

        att_row = QHBoxLayout()
        att_row.setSpacing(8)
        btn_add = QPushButton(_t("rla_attach_add"))
        btn_add.setObjectName("secondaryBtn")
        btn_add.setFixedHeight(28)
        btn_add.clicked.connect(self._add_attachments)
        btn_rm = QPushButton(_t("rla_attach_remove"))
        btn_rm.setObjectName("secondaryBtn")
        btn_rm.setFixedHeight(28)
        btn_rm.clicked.connect(self._remove_attachment)
        att_row.addWidget(btn_add)
        att_row.addWidget(btn_rm)
        att_row.addStretch()
        layout.addLayout(att_row)

        # Intake-gate feedback (the server's follow-up question), shown inline
        # so it stays readable while the user edits the description.
        self._gate_label = QLabel("")
        self._gate_label.setWordWrap(True)
        self._gate_label.setObjectName("gateLabel")
        self._gate_label.hide()
        layout.addWidget(self._gate_label)

        # Progress (hidden until upload)
        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        self._progress.hide()
        layout.addWidget(self._progress)

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._ok_btn = QPushButton(_t("rla_ok"))
        self._ok_btn.setObjectName("primaryBtn")
        self._ok_btn.setFixedWidth(110)
        self._ok_btn.setFixedHeight(32)
        self._ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton(_t("rla_cancel"))
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setFixedWidth(110)
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _apply_styles(self):
        self.setStyleSheet("""
        QDialog { background-color: #1e2936; }
        QLabel { color: #e6edf3; font-size: 13px; }
        QLabel#descLabel { color: #c9d1d9; font-size: 13px; }
        QLabel#sectionLabel { color: #e6edf3; font-size: 13px; font-weight: 600; }
        QLabel#statusLabel { color: #8b949e; font-size: 12px; }
        QLabel#gateLabel {
            color: #e3b341; font-size: 12px;
            background-color: #2b2213; border: 1px solid #5c4813;
            border-radius: 6px; padding: 8px;
        }
        QTextEdit#problemEdit {
            background-color: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px; font-size: 13px; padding: 6px;
        }
        QListWidget#skillList, QListWidget#attachList {
            background-color: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px; font-size: 13px; padding: 4px;
        }
        QListWidget#skillList::item, QListWidget#attachList::item {
            padding: 6px 8px; border-radius: 4px;
        }
        QListWidget#skillList::item:selected, QListWidget#attachList::item:selected {
            background-color: #1f6feb; color: white;
        }
        QListWidget::item:hover:!selected { background-color: #21262d; }
        QPushButton#primaryBtn {
            background-color: #238636; color: white; border: none;
            border-radius: 6px; font-weight: 600; font-size: 13px;
        }
        QPushButton#primaryBtn:hover { background-color: #2ea043; }
        QPushButton#primaryBtn:pressed { background-color: #1a7f37; }
        QPushButton#primaryBtn:disabled { background-color: #3d4448; color: #6e7681; }
        QPushButton#secondaryBtn {
            background-color: #21262d; color: #c9d1d9;
            border: 1px solid #30363d; border-radius: 6px; font-size: 12px;
        }
        QPushButton#secondaryBtn:hover { background-color: #30363d; }
        QPushButton#secondaryBtn:pressed { background-color: #161b22; }
        QProgressBar { background-color: #21262d; border: none; border-radius: 3px; }
        QProgressBar::chunk { background-color: #1f6feb; border-radius: 3px; }
        """)

    # ------------------------------------------------------------------
    # Skill loading
    # ------------------------------------------------------------------

    def _load_skills(self):
        self._skill_list.clear()
        skills = self._get_skills()
        if not skills:
            item = QListWidgetItem(_t("rla_no_skills"))
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self._skill_list.addItem(item)
            return
        for sid, name in skills:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, sid)
            self._skill_list.addItem(item)

    def _get_skills(self) -> list[tuple[str, str]]:
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
                    diagram_dir = skill_dir / "diagram_dir"
                    for json_file in (diagram_dir.glob("*.json") if diagram_dir.is_dir() else []):
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
            it = self._skill_list.item(i)
            if it.flags() & Qt.ItemIsEnabled:
                it.setSelected(True)

    def _deselect_all(self):
        self._skill_list.clearSelection()

    def _add_attachments(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, _t("rla_attach_dialog_title"), "",
            "Media (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.mp4 *.mov *.webm *.mkv *.avi);;All files (*.*)")
        for f in files:
            if f and f not in self._attachments:
                self._attachments.append(f)
                self._attach_list.addItem(QListWidgetItem(f))

    def _remove_attachment(self):
        for item in self._attach_list.selectedItems():
            path = item.text()
            if path in self._attachments:
                self._attachments.remove(path)
            self._attach_list.takeItem(self._attach_list.row(item))

    def _selected_skill_ids(self) -> List[str]:
        return [
            item.data(Qt.UserRole)
            for item in self._skill_list.selectedItems()
            if item.data(Qt.UserRole)
        ]

    def _show_gate(self, text: str):
        self._gate_label.setText(text)
        self._gate_label.show()
        self._problem_edit.setFocus()

    def _on_ok(self):
        """Step 1 of the sequence: pre-check locally, then ask the server."""
        description = self._problem_edit.toPlainText().strip()

        # Local pre-check — an obviously empty/thin description never costs a
        # server round-trip.
        from gui.ipc.w2p_handlers.debug_log_handler import local_description_issue
        issue = local_description_issue(description)
        if issue:
            self._show_gate(_t("rla_desc_required") if issue == "empty"
                            else _t("rla_desc_too_short"))
            return

        # Never auto-resubmit the same text: it just burns another classifier
        # call and comes back with the same question.
        if self._last_submitted is not None and description == self._last_submitted:
            self._show_gate(_t("rla_gate_edit_required"))
            return

        self._start_validation(description)

    def _start_validation(self, description: str):
        self._ok_btn.setEnabled(False)
        self._gate_label.hide()
        self._status_label.setText(_t("rla_checking"))
        self._status_label.show()
        self._progress.show()

        self._validator = _ValidateWorker(description, self._selected_skill_ids())
        self._validator.finished.connect(self._on_validated)
        self._validator.error.connect(self._on_validate_error)
        self._validator.start()

    def _on_validated(self, result: dict):
        """Step 2: ok -> confirm + upload, incomplete -> ask, rejected -> stop."""
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)

        description = self._problem_edit.toPlainText().strip()
        status = (result or {}).get("status") or "rejected"

        if status == "ok":
            self._grant = (result or {}).get("grant") or {}
            confirm = QMessageBox.question(
                self, _t("rla_confirm_title"),
                _t("rla_confirm_msg", n=len(self._attachments)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if confirm != QMessageBox.Yes:
                return
            self._start_upload(self._selected_skill_ids(), description,
                               list(self._attachments), self._grant)
            return

        # Either way the user must edit before we ask the server again.
        self._last_submitted = description

        if status == "rejected":
            QMessageBox.warning(self, _t("rla_gate_rejected_title"),
                                (result or {}).get("message") or _t("rla_gate_default_question"))
            return

        # incomplete
        self._gate_rounds += 1
        question = (result or {}).get("question") or _t("rla_gate_default_question")
        if self._gate_rounds >= self._MAX_GATE_ROUNDS:
            # Cap reached — hand off rather than loop forever.
            QMessageBox.information(self, _t("rla_gate_title"), _t("rla_gate_exhausted"))
            self._show_gate(_t("rla_gate_exhausted"))
            return
        self._show_gate(question)

    def _on_validate_error(self, error: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        QMessageBox.critical(self, _t("rla_failed_title"),
                             _t("rla_failed_msg", error=error))

    def _start_upload(self, skill_ids: List[str], description: str,
                      attachments: List[str], grant: Optional[dict] = None):
        self._ok_btn.setEnabled(False)
        self._status_label.setText(_t("rla_packaging"))
        self._status_label.show()
        self._progress.show()

        self._worker = _UploadWorker(skill_ids, description, attachments, grant)
        self._worker.finished.connect(self._on_upload_done)
        self._worker.error.connect(self._on_upload_error)
        self._worker.start()

    def _on_upload_done(self, message: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        # Lead with the localized success line (the server's message may be
        # English); append the server detail only when it carries something
        # beyond the generic English "uploaded successfully" fallback.
        body = _t("rla_complete_msg")
        detail = (message or "").strip()
        if detail and detail.lower().rstrip(".") != "debug package uploaded successfully":
            body = f"{body}\n\n{detail}"
        QMessageBox.information(self, _t("rla_complete_title"), body)
        self.accept()

    def _on_upload_error(self, error: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        QMessageBox.critical(self, _t("rla_failed_title"),
                             _t("rla_failed_msg", error=error))

    def closeEvent(self, event):
        for w in (self._validator, self._worker):
            if w and w.isRunning():
                w.quit()
                w.wait(3000)
        super().closeEvent(event)
