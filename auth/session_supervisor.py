"""
Session lifecycle supervisor.

Single source of truth for "is the IdP session currently usable, and when
will it stop being usable?".  Subscribers (offline sync, websocket clients,
etc.) register callbacks that fire on three transitions:

  - on_session_expiring_soon: token still valid but <S grace_remaining.
    Subscribers should flush whatever they're doing now.

  - on_session_refreshed: a new access_token was just installed.  Subscribers
    that paused work during the renewal window should resume.

  - on_session_expired: refresh failed and no usable token remains.
    Subscribers should drop any work that requires an IdP token.

This follows the standard OAuth refresh-token-rotation pattern described in
RFC 6749 §1.5 / §6: the IdP issues short-lived access tokens, a supervisor
in the client proactively rotates them via the refresh_token grant, and the
rest of the application depends only on the supervisor — never on raw
``self.tokens`` from the auth manager.

Why not do this inside ``AuthManager`` directly?  AuthManager has its own
periodic refresh task that does the right thing when a refresh_token is
present.  The supervisor adds three things AuthManager doesn't have today:

  1. Read the **actual JWT exp** instead of a fixed sleep interval, so a
     10-minute WeChat token triggers a refresh attempt at the right time.
  2. Fire events.  Downstream callers can pause/resume instead of polling
     or hitting "no auth token" errors.
  3. Expose ``get_valid_token()`` — a single, idempotent entry point that
     either returns a token or returns None with a clear semantic (re-login
     needed).  Removes the "did we clear tokens yet?" race.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("eCan.session_supervisor")


# Subscribers register callbacks with these signatures.
SessionExpiringCallback = Callable[[Dict[str, Any]], None]
SessionRefreshedCallback = Callable[[Dict[str, Any]], None]
SessionExpiredCallback = Callable[[], None]


class SessionSupervisor:
    """Coordinates proactive refresh + downstream event delivery."""

    # Token TTL below this triggers an immediate proactive refresh attempt.
    # RFC 6749 §6 leaves this to the implementer; 5 minutes is a common
    # desktop choice (long enough to absorb a flaky refresh request, short
    # enough that nothing visible flips to "expired" while we wait).
    REFRESH_LEAD_SECONDS = 300

    # Below this remaining lifetime we fire on_session_expiring_soon. UI
    # uses this to show a non-blocking "your session expires in 1 minute"
    # banner.  Distinct from REFRESH_LEAD_SECONDS so we can warn the user
    # earlier than we actually try to refresh.
    EXPIRING_SOON_SECONDS = 120

    def __init__(self, auth_manager: Any):
        self._am = auth_manager
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._on_expiring: List[SessionExpiringCallback] = []
        self._on_refreshed: List[SessionRefreshedCallback] = []
        self._on_expired: List[SessionExpiredCallback] = []

        # The most recently observed "exp" we have broadcast as
        # expiring-soon.  Tracked so we don't fire the same event every tick.
        self._last_expiring_fired: Optional[int] = None

        # Bookkeeping for the silent-refresh retry loop.  When we have
        # no refresh_token (CloudBase WeChat) and the token is about to
        # die, we drive an *attempt schedule* instead of a single shot
        # so that a transient failure (user closed the browser tab, no
        # network, etc.) doesn't force the user to log out — we just
        # retry until either the new token lands or the token actually
        # expires.  Off-the-record: this is the whole reason "silent
        # refresh" was a useful rename.
        self._silently_refreshing: bool = False
        self._silent_refresh_next_attempt: float = 0.0  # monotonic seconds
        self._silent_refresh_failures: int = 0

        # Wall-clock seconds (Unix time, not monotonic) of the most recent
        # token install via ``notify_token_installed``.  ``_drive_silent_refresh``
        # reads this to suppress the OAuth popup when a freshly installed
        # token gets rejected — almost always a CloudBase cache lag rather
        # than a real expiry, and popping a browser window at the user 30
        # seconds after they finished scanning the QR is a UX regression.
        self._last_token_installed_at: float = 0.0

    # ------------------------------------------------------------------
    # Subscription API
    # ------------------------------------------------------------------
    def on_session_expiring_soon(self, cb: SessionExpiringCallback) -> None:
        """Token still valid but close to expiry (about to attempt refresh)."""
        with self._lock:
            self._on_expiring.append(cb)

    def on_session_refreshed(self, cb: SessionRefreshedCallback) -> None:
        """New token installed.  Resume paused work."""
        with self._lock:
            self._on_refreshed.append(cb)

    def on_session_expired(self, cb: SessionExpiredCallback) -> None:
        """Refresh failed; user re-login required."""
        with self._lock:
            self._on_expired.append(cb)

    # ------------------------------------------------------------------
    # Synchronous public API for callers
    # ------------------------------------------------------------------
    def get_valid_token(self) -> Optional[str]:
        """Return a usable access_token, or None if the session is dead.

        Callers should treat None as "drop this work; the supervisor will
        notify you on_session_refreshed when you can resume."  Do NOT
        interpret None as a transient error — that path leads to retry
        storms.
        """
        am = self._am
        if not am or not getattr(am, "signed_in", False):
            return None
        tokens = getattr(am, "tokens", None) or {}
        candidate = tokens.get("AccessToken") or tokens.get("access_token")
        if not candidate:
            return None
        # Delegate to AuthManager.ensure_valid_tokens so the JWT-decoding
        # logic lives in exactly one place.
        try:
            ok = am.ensure_valid_tokens(
                min_validity_seconds=self.EXPIRING_SOON_SECONDS,
            )
        except Exception as exc:
            logger.warning(f"[SessionSupervisor] ensure_valid_tokens raised: {exc}")
            return candidate  # best-effort: token might still work for a few seconds
        if not ok:
            self._emit_expired()
            return None
        # ensure_valid_tokens may have rotated tokens in-place; re-read.
        tokens = getattr(am, "tokens", None) or {}
        return tokens.get("AccessToken") or tokens.get("access_token")

    # ------------------------------------------------------------------
    # Background supervisor loop
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="SessionSupervisor",
            daemon=True,
        )
        self._thread.start()
        logger.info("[SessionSupervisor] started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def notify_token_installed(self) -> None:
        """Call from AuthManager whenever a new token is installed
        (login, refresh, restore). Resets our internal state so the next
        loop tick uses the new exp instead of an old one. Also broadcasts
        on_session_refreshed so subscribers can resume work.
        """
        with self._lock:
            self._last_expiring_fired = None
            self._silent_refresh_failures = 0
            self._silent_refresh_next_attempt = 0.0
            self._silently_refreshing = False
            self._last_token_installed_at = time.time()
        self._emit_refreshed()

    def notify_session_cleared(self, source: str = "auth_manager") -> None:
        """Call from AuthManager after it has cleared stale credentials
        (token expired with no refresh_token, no silent refresh in flight,
        etc.).

        Without this, the supervisor's _tick early-exits at
        ``signed_in=False`` and never broadcasts ``on_session_expired``,
        so the GUI stays signed-in-looking while every cloud call 401s.

        Idempotent: callers may invoke this from multiple paths.
        """
        # Reset in-flight latch so a follow-up silent refresh attempt
        # can still be scheduled if some other code path cares.
        with self._lock:
            self._silently_refreshing = False
            self._silent_refresh_failures = 0
            self._silent_refresh_next_attempt = 0.0
        self._emit_expired()
        logger.info(
            f"[SessionSupervisor] notify_session_cleared (source={source}); "
            "fired on_session_expired for GUI logout redirect"
        )

    def notify_token_rejected(self, source: str = "") -> None:
        """Call from any caller (typically an AppSync client) that just
        received an UNAUTHENTICATED / "Invalid or expired access token"
        response.

        The supervisor's main loop only ticks every 30s and treats an
        already-expired token as a no-op (assuming AuthManager will clear
        it on the next ensure_valid_tokens() call).  But synchronous direct
        callers — IPC handlers that hit AppSync immediately after reading
        ``mainwin.get_auth_token()`` — never trigger ensure_valid_tokens,
        so without an explicit nudge the supervisor would only react on
        the next 30s tick AND even then would skip the expired path.

        This method runs a one-shot ``_tick`` on the calling thread, which:
          - if the token is within REFRESH_LEAD, attempts a refresh now;
          - if the token is already expired but we have a refresh_token,
            attempts a refresh anyway (the call already came back
            UNAUTHENTICATED, so the server disagrees with our local exp);
          - if we have no refresh_token, drives the silent WeChat re-auth.

        A nudge is treated as authoritative: if the server already rejected
        the token, we ignore any local ``remaining > REFRESH_LEAD_SECONDS``
        guard and force the refresh/silent path immediately.  Without this,
        a stale local TTL (e.g. local cache says 9 minutes left while the
        server says otherwise) would make the nudge a silent no-op.
        """
        logger.info(
            f"[SessionSupervisor] notify_token_rejected: source={source!r}; "
            f"running immediate refresh tick"
        )
        try:
            self._tick(force=True)
        except Exception as exc:
            logger.warning(
                f"[SessionSupervisor] notify_token_rejected tick raised: {exc}"
            )

    def _loop(self) -> None:
        tick_seconds = 30  # cheap check; precise scheduling happens inside ensure_valid_tokens
        while not self._stop.wait(timeout=tick_seconds):
            try:
                self._tick()
            except Exception as exc:
                logger.warning(f"[SessionSupervisor] tick error: {exc}")

    def _tick(self, force: bool = False) -> None:
        am = self._am
        if not am or not getattr(am, "signed_in", False):
            return

        tokens = getattr(am, "tokens", None) or {}
        candidate = tokens.get("AccessToken") or tokens.get("access_token")
        if not candidate:
            return

        exp = self._decode_exp(candidate)
        if exp is None:
            return
        now = int(time.time())
        remaining = exp - now

        # ``force`` means a caller (notify_token_rejected) just saw the
        # server reject this token.  Local exp is meaningless in that case
        # — the server is the source of truth — so collapse the remaining
        # window to zero for branch selection below.
        if force:
            logger.info(
                f"[SessionSupervisor] _tick force=True (server rejected token); "
                f"local remaining={remaining}s"
            )
            remaining = 0

        # 1) Already expired: try a refresh if we have a refresh_token, else
        #    fall through to silent-refresh (CloudBase WeChat). Returning
        #    without doing anything here assumes AuthManager will clear
        #    tokens on its next ensure_valid_tokens() call, but direct
        #    callers (IPC handlers doing synchronous AppSync requests) do
        #    NOT go through ensure_valid_tokens — they read tokens
        #    directly. Without this proactive attempt we just keep hitting
        #    UNAUTHENTICATED until the user restarts the app or the next
        #    legitimate ensure_valid_tokens happens to run.
        if remaining <= 0:
            refresh_token = (
                tokens.get("RefreshToken") or tokens.get("refresh_token")
            )
            if refresh_token:
                logger.info(
                    f"[SessionSupervisor] expired-token refresh: "
                    f"token has {remaining}s remaining but a call already "
                    f"came back UNAUTHENTICATED; forcing a refresh"
                )
                ok = self._attempt_refresh(refresh_token)
                if ok:
                    self._emit_refreshed()
                else:
                    self._emit_expired()
            else:
                # No refresh_token (CloudBase WeChat).  Drive a silent
                # silent-refresh loop.
                self._drive_silent_refresh(exp)
            return

        # 2) Within REFRESH_LEAD: try a refresh. Refreshed → emit
        #    on_session_refreshed. Failed → AuthManager clears tokens and
        #    sets signed_in=False; we follow up by emitting on_session_expired.
        if remaining <= self.REFRESH_LEAD_SECONDS:
            refresh_token = (
                tokens.get("RefreshToken") or tokens.get("refresh_token")
            )
            if refresh_token:
                logger.info(
                    f"[SessionSupervisor] proactive refresh: remaining={remaining}s"
                )
                ok = self._attempt_refresh(refresh_token)
                if ok:
                    self._emit_refreshed()
                else:
                    self._emit_expired()
            else:
                # No refresh_token (CloudBase WeChat).  Drive a silent
                # silent-refresh loop: ask the Application/Login layer
                # to re-run the WeChat OAuth flow in the background.
                # Subscribers (e.g. LoginoutGUI.prompt_for_reauth) are
                # idempotent and thread-guarded, so we can fire the
                # callback on every tick past the schedule without
                # worrying about double-prompts.
                self._drive_silent_refresh(exp)
            return

        # 3) Outside REFRESH_LEAD but inside EXPIRING_SOON: nudge the UI.
        if remaining <= self.EXPIRING_SOON_SECONDS:
            self._maybe_emit_expiring(exp)

    def _drive_silent_refresh(self, exp: int) -> None:
        """Token is rejected by the server AND no refresh_token is available.

        Background: CloudBase WeChat OAuth returns a 10-minute access
        token with **no refresh_token** (the only refresh API is the
        ``refresh_token`` grant, which requires a refresh token). When
        those 10 minutes run out, the only way to get a new access
        token is to replay the OAuth dance — which historically meant
        popping a browser window at the user.

        Per product policy (2026-08 revision), **eCan must never pop a
        browser window on its own**. The OAuth flow is only allowed
        when the user explicitly opens the login window — never as a
        background "silent re-auth" attempt.

        What this method does:

          1. If the token was installed very recently (< grace window)
             AND the local ``exp`` is still well in the future, the
             rejection is almost certainly a CloudBase cache lag
             (the upstream auth service doesn't see the freshly
             minted JWT for 30-60s). In that case we log + retry
             after the grace window — **do not** emit expired and
             **do not** kick the user out.

          2. Otherwise (real expiry or an old token still being
             rejected) log the situation, emit ``on_session_expired``
             so the GUI can render a "session expired" banner and
             enter its logged-out state. The user must re-login
             manually via the login window.

        We deliberately do NOT call ``_maybe_emit_expiring`` here.
        ``on_session_expiring_soon`` is wired to
        ``LoginoutGUI.prompt_for_reauth`` which spawns
        ``_start_reauth_flow`` → ``AuthManager.wechat_login()`` →
        ``webbrowser.open()`` — exactly the auto-popup we are banning.
        """
        FRESH_TOKEN_GRACE_SECONDS = 60
        wall_now = time.time()
        with self._lock:
            installed_at = self._last_token_installed_at
        token_age = wall_now - installed_at if installed_at > 0 else float("inf")
        remaining = exp - wall_now

        if (
            token_age < FRESH_TOKEN_GRACE_SECONDS
            and remaining > FRESH_TOKEN_GRACE_SECONDS
        ):
            logger.info(
                f"[SessionSupervisor] Suppressing on_session_expired for fresh "
                f"token: token is {int(token_age)}s old with {int(remaining)}s "
                f"local remaining (likely CloudBase 401 cache lag). Retrying "
                f"after grace window."
            )
            # Reschedule so the next tick (or next nudge) re-evaluates.
            with self._lock:
                self._silent_refresh_next_attempt = (
                    time.monotonic()
                    + FRESH_TOKEN_GRACE_SECONDS
                    - token_age
                )
            return

        logger.warning(
            "[SessionSupervisor] Session expired (no refresh_token); "
            "user must re-login manually. "
            f"token_age={int(token_age)}s remaining={int(remaining)}s exp={exp}"
        )
        # Clear the latches so subsequent tokens can install cleanly.
        with self._lock:
            self._silently_refreshing = False
            self._silent_refresh_next_attempt = 0.0
            self._silent_refresh_failures = 0
        # Notify subscribers (MainWindow etc.) so they can show a
        # "session expired" banner and route the user to the login
        # window. This is the only signal we emit — the OAuth popup
        # itself is intentionally never triggered here.
        self._emit_expired()

    def _maybe_emit_expiring(self, exp: int) -> None:
        with self._lock:
            if self._last_expiring_fired == exp:
                return
            self._last_expiring_fired = exp
            cbs = list(self._on_expiring)
        info = {"exp": exp}
        for cb in cbs:
            try:
                cb(info)
            except Exception as exc:
                logger.warning(f"[SessionSupervisor] on_session_expiring_soon cb failed: {exc}")

    def _emit_refreshed(self) -> None:
        with self._lock:
            cbs = list(self._on_refreshed)
        info = {
            "access_token": (self._am.tokens or {}).get("AccessToken"),
            "expires_at": self._decode_exp(
                (self._am.tokens or {}).get("AccessToken", "")
            ),
        }
        for cb in cbs:
            try:
                cb(info)
            except Exception as exc:
                logger.warning(f"[SessionSupervisor] on_session_refreshed cb failed: {exc}")

    def _emit_expired(self) -> None:
        with self._lock:
            cbs = list(self._on_expired)
        for cb in cbs:
            try:
                cb()
            except Exception as exc:
                logger.warning(f"[SessionSupervisor] on_session_expired cb failed: {exc}")

    def _attempt_refresh(self, refresh_token: str) -> bool:
        am = self._am
        try:
            result = am.cognito_service.refresh_tokens(refresh_token)
        except Exception as exc:
            logger.warning(f"[SessionSupervisor] refresh_tokens raised: {exc}")
            return False
        if not result.get("success"):
            logger.warning(
                f"[SessionSupervisor] refresh_tokens failed: "
                f"{result.get('error_code') or result.get('error')}"
            )
            # Mirror AuthManager's behaviour: a fatal refresh error means
            # the refresh_token itself is dead. Clear credentials so the
            # UI can show "please re-login".
            if result.get("error_code") in {"NotAuthorizedException", "InvalidParameterException"}:
                am.signed_in = False
                if am.tokens:
                    am.tokens = None
            return False
        with self._lock:
            am.tokens = (am.tokens or {}).copy()
            am.tokens.update(result["data"])
            self._last_expiring_fired = None
        return True

    def is_silent_refresh_in_flight(self) -> bool:
        """True when a background re-auth is currently being attempted.

        This is the gate the rest of the application uses to decide
        whether to keep credentials alive (and let the offline sync
        queue buffer writes) even though the access_token has just
        expired.  See ``AuthManager.ensure_valid_tokens`` for the
        only caller today.
        """
        with self._lock:
            return self._silently_refreshing

    @staticmethod
    def _decode_exp(jwt: str) -> Optional[int]:
        """Decode the ``exp`` claim without verifying the signature.

        Mirrors AuthManager._decode_token_expiry_unsafe so we don't depend
        on JWT library availability here.  Returns Unix seconds or None.

        Normalises millisecond ``exp`` claims to seconds — CloudBase / WeChat
        JWTs sign ``exp`` in milliseconds (~1e12), while standard JWT uses
        seconds (~1e9).  Without this normalisation the supervisor thinks the
        token has ~56 years left, every ``remaining <= REFRESH_LEAD_SECONDS``
        check fires, and the silent-WeChat-OAuth path triggers constantly,
        popping a browser window on every nudge.
        """
        if not jwt or jwt.count(".") < 1:
            return None
        try:
            import base64
            import json as _json
            payload_b64 = jwt.split(".")[1]
            # Pad to multiple of 4.
            payload_b64 += "=" * (-len(payload_b64) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
            exp = payload.get("exp")
            if exp is None:
                return None
            exp_int = int(exp)
            if exp_int > 10_000_000_000:
                exp_int //= 1000
            return exp_int
        except Exception:
            return None


# ----------------------------------------------------------------------
# Wiring
# ----------------------------------------------------------------------
_supervisor: Optional[SessionSupervisor] = None


def install_session_supervisor(auth_manager: Any) -> SessionSupervisor:
    """Create the singleton and bind it to ``auth_manager``. Idempotent."""
    global _supervisor
    if _supervisor is not None:
        return _supervisor
    _supervisor = SessionSupervisor(auth_manager)
    return _supervisor


def get_session_supervisor() -> Optional[SessionSupervisor]:
    return _supervisor