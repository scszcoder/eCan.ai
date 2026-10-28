"""Report Bug dialog.

A sequence, not a single submit: the user describes the problem, the description
goes through the server-side intake gate, and only an accepted description gets
packaged and uploaded.

    describe -> [local pre-check] -> validate (server) -> ok? -> confirm -> zip + upload
                                                       -> incomplete? -> ask, revise, retry
                                                       -> rejected? -> stop

The user picks the store (and optionally the agent/客服) the problem is about —
which the dialog turns into the involved skills behind the scenes — and may
attach screenshots / a screen recording; everything (skill files, referenced
prompts, the description saved to current_issues.md, the attachments, and the
full runlogs folder) is zipped and uploaded to support. All strings are
localized via ``gui.messages`` (CN default). The heavy lifting lives in the
shared ``debug_log_handler`` so the CLI (``ecan support upload``) and an agent
can do the same thing headlessly.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QProgressBar, QMessageBox, QComboBox, QTextEdit,
    QFileDialog, QRadioButton, QButtonGroup,
)

from gui.messages import get_message
from utils.logger_helper import logger_helper as logger


def _t(key: str, **kwargs) -> str:
    """Localized string, falling back to the key so a missing entry is visible."""
    return get_message(key, **kwargs) or key


# The server-side analyser anchors its log window on a clock time found in the
# description (the same shape as its own CLOCK_RE: 24-hour HH:MM). Without one
# it can only digest the newest generation of a log that rotates every 10 MB,
# which is usually not the generation the incident is in -- so the dialog asks
# for a time, and shows the user when it has one.
CLOCK_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)")


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
        # Set when the gate returned 'incomplete' WITH an upload grant. Its
        # presence is what turns the second click into a send rather than
        # another round of questions.
        self._warned_grant: dict = {}
        self._last_submitted: str | None = None
        self._grant: dict = {}
        self._setup_ui()
        self._apply_styles()
        self._load_stores()

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
        self._problem_edit.textChanged.connect(self._refresh_time_hint)
        layout.addWidget(self._problem_edit)

        # Time nudge: a hint that turns into an acknowledgement once the
        # description carries a clock time, plus one click for the common case
        # ("it just happened"). It never blocks -- a report without a time is
        # still worth having, it is just read less precisely.
        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        self._time_hint = QLabel(_t("rla_time_hint"))
        self._time_hint.setWordWrap(True)
        self._time_hint.setObjectName("timeHint")
        self._time_now_btn = QPushButton(_t("rla_time_now"))
        self._time_now_btn.setObjectName("secondaryBtn")
        self._time_now_btn.setFixedHeight(24)
        self._time_now_btn.clicked.connect(self._insert_now)
        time_row.addWidget(self._time_hint, stretch=1)
        time_row.addWidget(self._time_now_btn, alignment=Qt.AlignTop)
        layout.addLayout(time_row)

        # Priority — how urgent the reporter considers this issue. Rides into the
        # uploaded report as a tag on the description (no server field needed).
        layout.addWidget(self._section_label(_t("rla_priority_label")))
        prio_row = QHBoxLayout()
        prio_row.setSpacing(16)
        self._priority_group = QButtonGroup(self)
        # (code, label-key); order: most to least severe. Default = High priority.
        for code, key in (("urgent", "rla_priority_urgent"),
                          ("high", "rla_priority_high"),
                          ("annoying", "rla_priority_annoying")):
            rb = QRadioButton(_t(key))
            rb.setObjectName("priorityRadio")
            rb.setProperty("prioCode", code)
            if code == "high":
                rb.setChecked(True)
            self._priority_group.addButton(rb)
            prio_row.addWidget(rb)
        prio_row.addStretch()
        layout.addLayout(prio_row)

        # Store + agent — which store (and optionally which 客服/agent) the
        # problem is about. This replaces picking skills directly: a store scopes
        # the skill + prompt files bundled for support, and the agent dropdown is
        # filtered to the chosen store. Both ride into the report as description
        # tags so support sees the context even when no skill files resolve.
        layout.addWidget(self._section_label(_t("rla_store_label")))
        self._store_combo = QComboBox()
        self._store_combo.setObjectName("pickCombo")
        self._store_combo.currentIndexChanged.connect(self._on_store_changed)
        layout.addWidget(self._store_combo)

        layout.addWidget(self._section_label(_t("rla_agent_label")))
        self._agent_combo = QComboBox()
        self._agent_combo.setObjectName("pickCombo")
        layout.addWidget(self._agent_combo)
        layout.addStretch(1)

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

    def _refresh_time_hint(self):
        """Hint while there is no time, acknowledgement once there is one."""
        match = CLOCK_RE.search(self._problem_edit.toPlainText())
        self._time_hint.setText(_t("rla_time_ok", t=match.group(0)) if match
                                else _t("rla_time_hint"))
        self._time_hint.setProperty("state", "ok" if match else "")
        # Qt only re-evaluates a property selector on a re-polish.
        self._time_hint.style().unpolish(self._time_hint)
        self._time_hint.style().polish(self._time_hint)
        self._time_now_btn.setVisible(match is None)

    def _insert_now(self):
        """Append the current wall clock, in the 24-hour form the analyser reads."""
        text = self._problem_edit.toPlainText().rstrip()
        stamp = dt.datetime.now().strftime("%H:%M")
        self._problem_edit.setPlainText(f"{text} ({stamp})" if text else f"({stamp})")
        self._problem_edit.moveCursor(QTextCursor.End)
        self._problem_edit.setFocus()

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
        QLabel#timeHint { color: #8b949e; font-size: 12px; }
        QLabel#timeHint[state="ok"] { color: #3fb950; font-size: 12px; }
        QLabel#gateLabel {
            color: #e3b341; font-size: 12px;
            background-color: #2b2213; border: 1px solid #5c4813;
            border-radius: 6px; padding: 8px;
        }
        QTextEdit#problemEdit {
            background-color: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px; font-size: 13px; padding: 6px;
        }
        QRadioButton#priorityRadio { color: #e6edf3; font-size: 13px; spacing: 6px; }
        QRadioButton#priorityRadio::indicator { width: 14px; height: 14px; }
        QListWidget#attachList {
            background-color: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px; font-size: 13px; padding: 4px;
        }
        QListWidget#attachList::item { padding: 6px 8px; border-radius: 4px; }
        QListWidget#attachList::item:selected { background-color: #1f6feb; color: white; }
        QListWidget::item:hover:!selected { background-color: #21262d; }
        QComboBox#pickCombo {
            background-color: #161b22; color: #e6edf3;
            border: 1px solid #30363d; border-radius: 6px; font-size: 13px; padding: 6px 8px;
        }
        QComboBox#pickCombo:disabled { color: #6e7681; }
        QComboBox#pickCombo QAbstractItemView {
            background-color: #161b22; color: #e6edf3; selection-background-color: #1f6feb;
        }
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
    # Store + agent loading
    # ------------------------------------------------------------------

    def _load_stores(self):
        """Fill the store dropdown; the agent dropdown then follows the store."""
        self._overview: dict = {}       # {store_id: {"agents":[...], "tasks":[...]}}
        self._store_labels: dict = {}   # {store_id: display name}
        try:
            from app_context import AppContext
            from agent.ec_agents.store_overview import summarize_agents
            mainwin = AppContext.get_main_window()
            agents = (getattr(mainwin, "agents", None) or []) if mainwin else []
            self._overview = summarize_agents(agents)
            svc = getattr(getattr(mainwin, "ec_db_mgr", None), "store_service", None)
            for s in (svc.list_stores() if svc else []):
                sid = str(s.get("store_id") or "")
                if sid:
                    self._store_labels[sid] = str(s.get("name") or sid)
        except Exception as exc:
            logger.warning(f"[RequestLogAnalysis] store/agent load failed: {exc}")

        self._store_combo.blockSignals(True)
        self._store_combo.clear()
        # First entry: the report need not be tied to a store (never blocks a
        # filing — the full runlogs upload stands on its own).
        self._store_combo.addItem(_t("rla_store_any"), "")
        # Every store we have a name for, plus any store seen only in memory
        # (has agents serving it but no local catalog row yet).
        ids = list(self._store_labels.keys())
        ids += [sid for sid in self._overview if sid not in self._store_labels]
        for sid in ids:
            self._store_combo.addItem(self._store_labels.get(sid, sid), sid)
        self._store_combo.blockSignals(False)
        self._on_store_changed()

    def _on_store_changed(self):
        """Repopulate the agent dropdown with the chosen store's agents."""
        store_id = self._store_combo.currentData() or ""
        self._agent_combo.clear()
        self._agent_combo.addItem(_t("rla_agent_any"), "")
        for a in (self._overview.get(store_id, {}).get("agents") or []) if store_id else []:
            if a.get("id"):
                self._agent_combo.addItem(str(a.get("name") or a.get("id")), a.get("id"))
        # Only meaningful to narrow by agent when a store with agents is chosen.
        self._agent_combo.setEnabled(bool(store_id) and self._agent_combo.count() > 1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

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

    def _derive_skill_ids(self) -> List[str]:
        """Skill ids used by the chosen store (optionally narrowed to one agent),
        so support still gets the relevant skill + prompt files. Empty when no
        store is chosen — the full runlogs upload is the primary payload."""
        store_id = self._store_combo.currentData() or ""
        if not store_id:
            return []
        agent_id = self._agent_combo.currentData() or ""
        ids: List[str] = []
        try:
            from app_context import AppContext
            from agent.ec_agents.store_overview import _task_store_id
            mainwin = AppContext.get_main_window()
            for agent in ((getattr(mainwin, "agents", None) or []) if mainwin else []):
                aid = getattr(getattr(agent, "card", None), "id", "") or ""
                if agent_id and aid != agent_id:
                    continue
                for task in list(getattr(agent, "tasks", None) or []):
                    if _task_store_id(task) != store_id:
                        continue
                    sid = getattr(getattr(task, "skill", None), "id", None)
                    if sid and sid not in ids:
                        ids.append(sid)
        except Exception as exc:
            logger.warning(f"[RequestLogAnalysis] skill derivation failed: {exc}")
        return ids

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

        # Same text again = the user read the question and chose to send anyway.
        # The gate WARNS, it does not block: the payload of this report is the log
        # bundle, and a thin description with full logs is still worth having. A
        # customer who wrote something and was turned away simply does not file
        # the next one. Only 'rejected' (empty / abuse) actually stops here.
        if self._last_submitted is not None and description == self._last_submitted:
            if self._warned_grant:
                self._start_upload(self._derive_skill_ids(), description,
                                   list(self._attachments), self._warned_grant)
                return
            # No grant to proceed with (an older backend): re-asking the same text
            # would just burn another classifier call for the same question.
            self._show_gate(_t("rla_gate_edit_required"))
            return

        self._start_validation(description)

    def _start_validation(self, description: str):
        self._ok_btn.setEnabled(False)
        self._gate_label.hide()
        self._status_label.setText(_t("rla_checking"))
        self._status_label.show()
        self._progress.show()

        self._validator = _ValidateWorker(description, self._derive_skill_ids())
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

        # "offline": not logged in -- the report is packaged and uploads by itself later.
        if status in ("ok", "offline"):
            self._grant = (result or {}).get("grant") or {}
            confirm = QMessageBox.question(
                self, _t("rla_confirm_title"),
                _t("rla_confirm_msg", n=len(self._attachments)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if confirm != QMessageBox.Yes:
                return
            self._start_upload(self._derive_skill_ids(), description,
                               list(self._attachments), self._grant)
            return

        # Either way the user must edit before we ask the server again.
        self._last_submitted = description

        if status == "rejected":
            QMessageBox.warning(self, _t("rla_gate_rejected_title"),
                                (result or {}).get("message") or _t("rla_gate_default_question"))
            return

        # incomplete — warn, and keep the grant so the next click can proceed.
        self._gate_rounds += 1
        self._warned_grant = (result or {}).get("grant") or {}
        question = (result or {}).get("question") or _t("rla_gate_default_question")
        if self._gate_rounds >= self._MAX_GATE_ROUNDS:
            # Cap reached — hand off rather than loop forever.
            QMessageBox.information(self, _t("rla_gate_title"), _t("rla_gate_exhausted"))
            self._show_gate(_t("rla_gate_exhausted"))
            return
        # Say that it is optional. A question with no way past it reads as a
        # refusal, which is exactly how a customer stops filing bug reports.
        hint = "\n" + _t("rla_gate_send_anyway") if self._warned_grant else ""
        self._show_gate(question + hint)

    def _on_validate_error(self, error: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        QMessageBox.critical(self, _t("rla_failed_title"),
                             _t("rla_failed_msg", error=error))

    def _priority_label(self) -> str:
        """The checked priority's localized label (defaults to High priority)."""
        btn = self._priority_group.checkedButton()
        code = btn.property("prioCode") if btn else "high"
        return _t({"urgent": "rla_priority_urgent",
                   "high": "rla_priority_high",
                   "annoying": "rla_priority_annoying"}.get(code, "rla_priority_high"))

    def _context_tag(self) -> str:
        """Store/agent tags for the uploaded description (only the parts chosen)."""
        parts = []
        if self._store_combo.currentData():
            parts.append(_t("rla_store_tag", s=self._store_combo.currentText()))
        if self._agent_combo.currentData():
            parts.append(_t("rla_agent_tag", a=self._agent_combo.currentText()))
        return "".join(parts)

    def _tagged_description(self, description: str) -> str:
        """Prepend the chosen context (store/agent) and priority so they ride into
        the uploaded report (the server stores the description; there is no
        separate field)."""
        tag = self._context_tag() + _t("rla_priority_tag", p=self._priority_label())
        return f"{tag} {description}".strip()

    def _start_upload(self, skill_ids: List[str], description: str,
                      attachments: List[str], grant: Optional[dict] = None):
        self._ok_btn.setEnabled(False)
        self._status_label.setText(_t("rla_packaging"))
        self._status_label.show()
        self._progress.show()

        description = self._tagged_description(description)
        self._worker = _UploadWorker(skill_ids, description, attachments, grant)
        self._worker.finished.connect(self._on_upload_done)
        self._worker.error.connect(self._on_upload_error)
        self._worker.start()

    def _on_upload_done(self, message: str):
        self._progress.hide()
        self._status_label.hide()
        self._ok_btn.setEnabled(True)
        from gui.ipc.w2p_handlers.debug_log_handler import QUEUED_MARK
        if (message or "").startswith(QUEUED_MARK):
            # Saved for a background upload (not logged in / connection cut off).
            QMessageBox.information(self, _t("rla_queued_title"), _t("rla_queued_msg"))
            self.accept()
            return
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
