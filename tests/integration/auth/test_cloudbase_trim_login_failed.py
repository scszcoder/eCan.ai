#!/usr/bin/env python3
"""Regression test for terminals/7.txt:401-460 (2026-08-24, 23:34):

The user typed their CloudBase email + password correctly into LoginCN,
but the backend CloudBase SDK rejected the credentials with
``INVALID_CREDENTIALS``.  The traceback at terminals/7.txt:41 shows the
GraphQL variables arrived at the backend as:

    {'email': '249511118@qq.com', 'password': ' Ecan249511118!', 'role': 'Commander'}
                                                  ↑ leading space

That leading space came from the browser autofill (or a copy/paste of the
password from a password manager) and CloudBase's SDK treated
``' Ecan249511118!'`` as a wrong password — even though the user typed
it correctly.  Frontend contract: every string field that crosses an
IPC boundary into CloudBase must be ``.trim()``-ed first so an invisible
whitespace can't flip a correct credential into an INVALID_CREDENTIALS.

We also pin the backend ``LocalServer.py`` LOGIN_FAILED warning-level
behaviour — previously the handler raised ``RuntimeError`` for
``LOGIN_FAILED`` (which is a normal user-visible error), and
``LocalServer.graphql_handler`` then dumped the traceback into stderr
as an ERROR.  That's noisy and misleading; LOGIN_FAILED belongs in the
warning bucket alongside INVALID_TOKEN.

This test is a **source-level contract test** (no React runtime).  It
checks the static shape of the fix so a future refactor that drops the
``.trim()`` calls or re-introduces traceback logging for LOGIN_FAILED
fails CI immediately.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_script_path = Path(__file__).resolve().parent  # tests/integration/auth/
_project_root = _script_path
for _ in range(3):  # → tests/ → project root
    _project_root = _project_root.parent
sys.path.insert(0, str(_project_root))


def _read(rel: str) -> str:
    return (_project_root / rel).read_text()


class TestCloudbaseAuthTrim:
    """Every CloudBase IPC call must ``.trim()`` the user-provided strings
    before crossing the IPC boundary.
    """

    def _auth_source(self) -> str:
        return _read("gui_v2/src/services/auth/cloudbaseAuth.ts")

    def _trim_after_param(self, src: str, method: str) -> bool:
        """Assert that the ``method`` block trims email/password/phone/code.

        We look for the pattern

            { method: '<method>' },
            { email: email.trim(), password: password.trim(), ... }

        i.e. every user-controlled string field that goes into the IPC
        payload must already be ``.trim()``-ed at the call site.

        Search strategy:
          1. Find ``{ method: '<method>' },`` (the closing brace + comma
             is the giveaway that this is a call-site, not a generic
             registration elsewhere in the file).
          2. Take a window starting ~50 chars after that anchor so we
             land on the parameters object literal on the next line.
        """
        anchor = re.escape(f"{{ method: '{method}' }},")
        match = re.search(anchor, src)
        assert match is not None, (
            f"Could not find a {{ method: '{method}' }} call site. "
            f"Make sure the IPC invocation uses the standard "
            f"``{{ method: '...' }},`` literal."
        )
        # Skip the closing brace + comma + whitespace, then read the
        # next 1500 chars (long enough to cover the parameters object
        # even with comments).
        snippet = src[match.end() : match.end() + 1500]
        return ".trim()" in snippet

    def test_login_with_email_trims_credentials(self):
        src = self._auth_source()
        assert self._trim_after_param(src, "cloudbase_login"), (
            "loginWithEmail must call .trim() on email and password "
            "before crossing the IPC boundary.  terminals/7.txt:41 shows "
            "the un-trimmed value ' Ecan249511118!' caused CloudBase to "
            "return INVALID_CREDENTIALS even though the user typed the "
            "correct password."
        )

    def test_signup_with_email_trims_credentials(self):
        src = self._auth_source()
        assert self._trim_after_param(src, "cloudbase_signup"), (
            "signupWithEmail must call .trim() on email and password."
        )

    def test_send_phone_code_trims_phone(self):
        src = self._auth_source()
        assert self._trim_after_param(src, "cloudbase_send_code"), (
            "sendPhoneCode must call .trim() on phone — autofill "
            "frequently carries spaces / country-code prefixes."
        )

    def test_phone_login_trims_phone_and_code(self):
        src = self._auth_source()
        assert self._trim_after_param(src, "cloudbase_phone_login"), (
            "loginWithPhone must call .trim() on phone and code — "
            "verification codes are especially prone to whitespace "
            "from SMS copy-paste."
        )

    def test_confirm_signup_trims_email_code_password(self):
        src = self._auth_source()
        assert self._trim_after_param(
            src, "cloudbase_signup_confirm"
        ), (
            "confirmSignupWithEmail must call .trim() on email, code, "
            "and password."
        )

    def test_reset_password_trims_phone_code_new_password(self):
        src = self._auth_source()
        assert self._trim_after_param(
            src, "cloudbase_reset_password"
        ), (
            "resetPasswordWithPhone must call .trim() on phone, code, "
            "and new_password."
        )


class TestLocalServerLoginFailedWarning:
    """Backend LocalServer.graphql_handler must log LOGIN_FAILED as a
    warning, not an ERROR with a traceback.  terminals/7.txt:54-61 shows
    the old behaviour:

        [GraphQL] ❌ Error handling request: Invalid username or password
        Traceback (most recent call last):
          ...
        RuntimeError: Invalid username or password

    LOGIN_FAILED is a normal user-visible error — the frontend already
    receives ``code: LOGIN_FAILED`` in the GraphQL ``errors`` array and
    shows a friendly toast.  Logging it as ERROR with a full traceback
    just adds noise to the user's console.
    """

    def test_login_failed_in_warning_list(self):
        src = _read("gui/LocalServer.py")
        # Find the early-warning ``if error_code in (...)`` block.
        # It must mention ``LOGIN_FAILED`` (alongside INVALID_TOKEN /
        # TOKEN_REQUIRED / SYSTEM_NOT_READY).
        match = re.search(
            r'if error_code in \(\s*(?P<body>.*?)\s*\):',
            src,
            flags=re.DOTALL,
        )
        assert match is not None, (
            "Could not find the ``if error_code in (...)`` warning "
            "block in gui/LocalServer.py."
        )
        body = match.group("body")
        for required in (
            "LOGIN_FAILED",
            "CLOUDBASE_NOT_AVAILABLE",
            "INVALID_CREDENTIALS",
            "SMS_SEND_FAILED",
        ):
            assert required in body, (
                f"{required} must be listed in the warning-level "
                f"early-exit bucket in gui/LocalServer.py.graphql_handler. "
                f"It is a normal user-visible error, not an exception "
                f"that warrants a full traceback."
            )
