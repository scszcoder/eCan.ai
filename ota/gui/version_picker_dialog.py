"""Multi-version picker dialog for the OTA "Check for new release" flow.

See ``ota/docs/multi_version_picker.md`` for the end-to-end design. In
short: when the appcast yields **more than one** eligible item for the
current user (i.e. there are several user-tagged builds newer than the
installed version, or a mix of universal + user-tagged), the single-
version confirmation dialog in ``WebGUI._show_update_confirmation`` is
no longer enough — the user needs to *pick* which build they want. This
module provides that picker.

Shape of ``available_versions`` (as produced by
``ota.core.appcast.item_to_update_dict``)::

    {
        "version": "songc_v26.05.04.09.11",
        "version_core": "v26.05.04.09.11",
        "user_prefix": "songc",   # or None for universal builds
        "download_url": "...",
        "alternate_url": "...",   # S3-accelerate variant, may be None
        "file_size": 12345,
        "signature": "...",
        "description": "<html>...</html>",
        "pub_date": "Fri, 02 May 2026 22:22:00 GMT",
        "os": "windows",
        "arch": "amd64",
    }

The picker never mutates the list it receives; when the user accepts,
it emits ``version_selected`` with a **synthesized single-version
``update_info`` dict** that downstream code (``WebGUI._start_ota_update``
and ``ota.gui.update_dialog.UpdateDialog``) can consume unmodified.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from utils.logger_helper import logger_helper as logger

from .i18n import get_translator


def _format_size(size_bytes: int) -> str:
    """Render a byte count as a human-readable string (KB/MB/GB)."""
    if not size_bytes or size_bytes <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"


def _build_single_version_update_info(
    picked: Dict[str, Any],
    source_update_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Shape a picked item into the legacy ``update_info`` dict.

    Keeps every key ``WebGUI._start_ota_update`` and
    ``UpdateDialog`` expect (``latest_version``, ``download_url``,
    ``alternate_url``, ``file_size``, ``signature``, ``description``,
    ``source``, ``update_available``) pointing at the picked item —
    *not* at ``source_update_info['available_versions'][0]`` — so the
    user's choice actually drives the install.

    We still preserve the original ``available_versions`` list for
    anyone further downstream who cares (e.g. diagnostic logging), and
    flag the synthesis with ``update_info['picked_from_list'] = True``
    for easier tracing.
    """
    return {
        **source_update_info,
        "update_available": True,
        "latest_version": picked["version"],
        "download_url": picked["download_url"],
        "alternate_url": picked.get("alternate_url"),
        "file_size": picked.get("file_size", 0),
        "signature": picked.get("signature", ""),
        "description": picked.get("description", ""),
        # Tag the synthesis so logs can distinguish "LLM picked this"
        # from "auto-latest picked this".
        "picked_from_list": True,
        "picked_user_prefix": picked.get("user_prefix"),
    }


class VersionPickerDialog(QDialog):
    """List-style dialog that lets the user pick from multiple eligible builds.

    Emits ``version_selected(update_info_dict)`` on accept. Callers
    typically connect the signal to ``WebGUI._start_ota_update``
    directly, or use the blocking convenience wrapper
    :func:`pick_version_and_install`.
    """

    version_selected = Signal(dict)

    def __init__(
        self,
        parent: Optional[QWidget],
        available_versions: List[Dict[str, Any]],
        source_update_info: Dict[str, Any],
        current_version: str = "",
        user_prefix: Optional[str] = None,
    ) -> None:
        super().__init__(parent)

        # Defensive copy so the dialog can't accidentally mutate the
        # caller's list (e.g. by reordering via QListWidget).
        self._versions: List[Dict[str, Any]] = list(available_versions)
        self._source_update_info: Dict[str, Any] = dict(source_update_info)
        self._current_version = current_version or ""
        self._user_prefix = (user_prefix or "").strip() or None

        self._tr = get_translator()
        self.setWindowTitle(self._tr.tr("picker_title"))
        self.setMinimumSize(640, 480)

        self._build_ui()
        self._populate_list()
        # Default-select the newest (index 0) so the single-click flow
        # still works for the common case.
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header: "3 newer version(s) available for you" (+ user if tagged).
        if self._user_prefix:
            header_text = self._tr.tr("picker_header_tagged").format(
                count=len(self._versions), user=self._user_prefix
            )
        else:
            header_text = self._tr.tr("picker_header").format(
                count=len(self._versions)
            )
        header = QLabel(f"<h3>{header_text}</h3>")
        header.setTextFormat(Qt.RichText)
        root.addWidget(header)

        # Sub-header: "current version: X.Y.Z"
        if self._current_version:
            cur = QLabel(
                self._tr.tr("current_version_label").format(
                    version=self._current_version
                )
            )
            root.addWidget(cur)

        # Instruction
        root.addWidget(QLabel(self._tr.tr("picker_pick_instruction")))

        # List of versions
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(
            """
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background-color: #007AFF; color: white; }
            """
        )
        self._list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self._list, 1)

        # Release notes panel for the selected item
        self._notes = QTextEdit()
        self._notes.setReadOnly(True)
        self._notes.setMinimumHeight(120)
        self._notes.setMaximumHeight(220)
        root.addWidget(self._notes)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch(1)

        self._later_btn = QPushButton(self._tr.tr("remind_later"))
        self._later_btn.clicked.connect(self.reject)
        button_row.addWidget(self._later_btn)

        self._install_btn = QPushButton(self._tr.tr("picker_install_selected"))
        self._install_btn.setDefault(True)
        self._install_btn.clicked.connect(self._on_install_clicked)
        button_row.addWidget(self._install_btn)

        root.addLayout(button_row)

    def _populate_list(self) -> None:
        """Render ``self._versions`` into the QListWidget.

        Format per row::

            [BADGE]  <version>   <pub_date>   <size>

        Where ``BADGE`` is either ``UNIVERSAL`` (no prefix) or
        ``FOR <user>`` (tagged build). The version string is the raw
        ``version`` field so users can copy-paste it into bug reports.
        """
        for entry in self._versions:
            up = entry.get("user_prefix")
            if up:
                badge = self._tr.tr("picker_user_badge").format(user=up)
            else:
                badge = self._tr.tr("picker_universal_badge")

            label = (
                f"[{badge}]  {entry.get('version', '?'):<30}  "
                f"{entry.get('pub_date') or '—':<32}  "
                f"{_format_size(int(entry.get('file_size') or 0))}"
            )
            item = QListWidgetItem(label)
            # Store the full entry on the item so _on_row_changed /
            # _on_install_clicked can recover it without index math.
            item.setData(Qt.UserRole, entry)
            self._list.addItem(item)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._versions):
            self._notes.clear()
            return
        entry = self._versions[row]
        html = entry.get("description") or ""
        if html.strip():
            self._notes.setHtml(html)
        else:
            self._notes.setPlainText(self._tr.tr("picker_no_release_notes"))

    def _on_install_clicked(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._versions):
            # Should not happen — guard anyway.
            logger.warning("[VersionPickerDialog] Install clicked with no selection")
            return
        picked = self._versions[row]
        synthesized = _build_single_version_update_info(
            picked, self._source_update_info
        )
        logger.info(
            "[VersionPickerDialog] User picked version=%r user_prefix=%r "
            "(out of %d eligible)",
            picked.get("version"),
            picked.get("user_prefix"),
            len(self._versions),
        )
        self.version_selected.emit(synthesized)
        self.accept()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def selected_update_info(self) -> Optional[Dict[str, Any]]:
        """Return the synthesized update_info for the picked version.

        ``None`` when the dialog was rejected / closed without a pick.
        Useful for callers that want a blocking ``exec()`` + read-back
        pattern instead of wiring up the :attr:`version_selected` signal.
        """
        row = self._list.currentRow()
        if row < 0 or self.result() != QDialog.Accepted:
            return None
        picked = self._versions[row]
        return _build_single_version_update_info(picked, self._source_update_info)


def pick_version_and_install(
    parent: Optional[QWidget],
    update_info: Dict[str, Any],
    current_version: str,
    install_cb: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Show the picker and, on accept, hand off to ``install_cb``.

    ``install_cb`` is typically ``WebGUI._start_ota_update`` — the same
    entry point the single-version confirmation dialog uses, so the
    multi-version path reuses the entire existing download / install
    pipeline without modification. Signature: ``install_cb(version, info)``.
    """
    versions = update_info.get("available_versions") or []
    if not versions:
        logger.warning("[VersionPickerDialog] No available_versions to pick from")
        return

    dialog = VersionPickerDialog(
        parent=parent,
        available_versions=versions,
        source_update_info=update_info,
        current_version=current_version,
        user_prefix=update_info.get("user_prefix"),
    )

    def _on_picked(info: Dict[str, Any]) -> None:
        try:
            install_cb(info.get("latest_version", ""), info)
        except Exception as exc:  # defensive — must not leak into caller
            logger.error(
                "[VersionPickerDialog] install_cb raised: %s", exc, exc_info=True
            )

    dialog.version_selected.connect(_on_picked)
    dialog.exec()
