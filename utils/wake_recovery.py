#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wake Recovery Manager

Coordinates application recovery after the system wakes from sleep.
Registered as a callback on PowerMonitor.on_wake() so it runs automatically.

Recovery steps (in order):
    1. Refresh auth tokens (they may have expired during sleep)
    2. Restart WAN WebSocket subscriptions (TCP connections are dead after sleep)
    3. Nudge the scheduler to immediately check for missed scheduled tasks
    4. Re-acquire sleep inhibitor if tasks are still running

All steps are best-effort with logging — a failure in one step does not
block the others.
"""

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gui.MainGUI import MainWindow

logger = logging.getLogger(__name__)

# Minimum sleep duration (seconds) before triggering full recovery.
# Short sleeps (< 30s) usually don't break connections.
_MIN_RECOVERY_SLEEP_SEC = 30.0


class WakeRecoveryManager:
    """Orchestrates post-wake recovery for the application.

    Designed to be instantiated once and attached to PowerMonitor via:
        power_monitor.on_wake(manager.on_wake)
        power_monitor.on_sleep(manager.on_sleep)

    TODO(cli-task-execution): When CLI mode supports running/scheduling tasks,
        this class currently depends on MainWindow for auth_manager, agents,
        and WAN state. For headless CLI, create a lightweight CLIContext that
        provides:
        - auth_manager  (for token refresh — Step 1)
        - agents list   (for scheduler nudge — Step 3)
        - active_tasks  (for sleep inhibitor — Step 4)
        Step 2 (WAN subscriptions) can be skipped in CLI mode unless CLI
        needs real-time cloud push. Accept Union[MainWindow, CLIContext]
        instead of MainWindow.
    """

    def __init__(self, mainwin: "MainWindow"):
        self._mainwin = mainwin
        self._recovering = False

    # ------------------------------------------------------------------
    # Callbacks (registered on PowerMonitor)
    # ------------------------------------------------------------------

    def on_sleep(self) -> None:
        """Called just before the system sleeps.

        Logs current state for diagnostics. Could be extended to
        checkpoint in-flight work.
        """
        mw = self._mainwin
        try:
            agent_count = len(mw.agents) if hasattr(mw, 'agents') else 0
            wan_ok = getattr(mw, 'wan_connected', False)
            logger.info(
                f"[WakeRecovery] Preparing for sleep — "
                f"agents={agent_count}, wan_connected={wan_ok}"
            )
        except Exception as e:
            logger.debug(f"[WakeRecovery] on_sleep logging error: {e}")

    def on_wake(self, sleep_duration: float) -> None:
        """Called when the system wakes up.

        Args:
            sleep_duration: approximate seconds the machine was asleep.
        """
        if sleep_duration < _MIN_RECOVERY_SLEEP_SEC:
            logger.info(
                f"[WakeRecovery] Short sleep ({sleep_duration:.1f}s < "
                f"{_MIN_RECOVERY_SLEEP_SEC}s) — skipping full recovery"
            )
            return

        if self._recovering:
            logger.warning("[WakeRecovery] Recovery already in progress — skipping")
            return

        # Run recovery in a background thread to avoid blocking the Qt main thread
        t = threading.Thread(
            target=self._run_recovery,
            args=(sleep_duration,),
            name="WakeRecovery",
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------
    # Recovery pipeline
    # ------------------------------------------------------------------

    def _run_recovery(self, sleep_duration: float) -> None:
        self._recovering = True
        start = time.time()
        logger.info(
            f"[WakeRecovery] Starting recovery after {sleep_duration:.0f}s sleep..."
        )

        try:
            self._step_refresh_tokens()
            self._step_restart_wan_subscriptions()
            self._step_nudge_scheduler()
            self._step_reacquire_sleep_inhibitor()
        except Exception as e:
            logger.error(f"[WakeRecovery] Unexpected error during recovery: {e}")
        finally:
            elapsed = time.time() - start
            logger.info(f"[WakeRecovery] Recovery completed in {elapsed:.1f}s")
            self._recovering = False

    # ------------------------------------------------------------------
    # Step 1: Refresh auth tokens
    # ------------------------------------------------------------------

    def _step_refresh_tokens(self) -> None:
        """Force an immediate token refresh via AuthManager."""
        try:
            mw = self._mainwin
            auth_mgr = getattr(mw, 'auth_manager', None)
            if auth_mgr is None:
                logger.debug("[WakeRecovery] No auth_manager on mainwin — skipping token refresh")
                return

            tokens = auth_mgr.get_tokens()
            if not tokens:
                logger.debug("[WakeRecovery] No tokens stored — skipping refresh")
                return

            refresh_token = tokens.get('RefreshToken') or tokens.get('refresh_token')
            if not refresh_token:
                logger.warning("[WakeRecovery] No refresh token available — cannot refresh")
                return

            logger.info("[WakeRecovery] Step 1: Refreshing auth tokens...")
            result = auth_mgr.cognito_service.refresh_tokens(refresh_token)

            if result.get('success'):
                auth_mgr.tokens.update(result['data'])
                logger.info("[WakeRecovery] Step 1: Tokens refreshed successfully")
            else:
                logger.warning(
                    f"[WakeRecovery] Step 1: Token refresh failed: {result.get('error')}"
                )
        except Exception as e:
            logger.error(f"[WakeRecovery] Step 1 error: {e}")

    # ------------------------------------------------------------------
    # Step 2: Restart WAN WebSocket subscriptions
    # ------------------------------------------------------------------

    def _step_restart_wan_subscriptions(self) -> None:
        """Restart WAN subscriptions for all agents.

        The existing subscription loops have their own retry logic, but
        after a sleep the TCP connection is dead and the recv() call is
        blocked. We mark the connection as disconnected so the retry
        loop in wan_a2a_subscribe / subscribeToWanChat will break out
        of its recv and reconnect faster.
        """
        try:
            mw = self._mainwin

            # Mark WAN as disconnected — this causes the recv loops to
            # break out and trigger their retry/reconnect logic.
            if hasattr(mw, 'set_wan_connected'):
                was_connected = getattr(mw, 'wan_connected', False)
                mw.set_wan_connected(False)
                if hasattr(mw, 'set_wan_msg_subscribed'):
                    mw.set_wan_msg_subscribed(False)
                logger.info(
                    f"[WakeRecovery] Step 2: Marked WAN disconnected "
                    f"(was {'connected' if was_connected else 'disconnected'})"
                )

            # Restart WAN subscriptions for each agent
            agents = getattr(mw, 'agents', [])
            restarted = 0
            for agent in agents:
                try:
                    if hasattr(agent, '_start_wan_subscriptions'):
                        agent._start_wan_subscriptions()
                        restarted += 1
                except Exception as e:
                    agent_name = getattr(agent, 'name', '?')
                    if hasattr(agent, 'card') and agent.card:
                        agent_name = agent.card.name
                    logger.warning(
                        f"[WakeRecovery] Step 2: Failed to restart WAN for "
                        f"agent '{agent_name}': {e}"
                    )

            logger.info(
                f"[WakeRecovery] Step 2: Restarted WAN subscriptions for "
                f"{restarted}/{len(agents)} agents"
            )
        except Exception as e:
            logger.error(f"[WakeRecovery] Step 2 error: {e}")

    # ------------------------------------------------------------------
    # Step 3: Nudge the scheduler
    # ------------------------------------------------------------------

    def _step_nudge_scheduler(self) -> None:
        """Wake up the scheduler so it immediately checks for missed tasks.

        Each agent's TaskRunner has a _stop_event threading.Event.
        Setting and clearing it causes the runner's poll loop to
        wake up from its sleep() and re-evaluate the schedule.
        
        For runners that use an event/condition variable for their
        scheduling poll, we set the timer service to trigger an
        immediate check.
        """
        try:
            mw = self._mainwin
            agents = getattr(mw, 'agents', [])
            nudged = 0

            for agent in agents:
                try:
                    runner = getattr(agent, 'runner', None)
                    if runner is None:
                        continue

                    # If the runner has a timer service, trigger immediate check
                    timer_svc = getattr(runner, '_timer_service', None)
                    if timer_svc and hasattr(timer_svc, 'trigger_immediate_check'):
                        timer_svc.trigger_immediate_check()
                        nudged += 1
                        continue

                    # Fallback: if runner uses a threading.Event for its loop,
                    # set it briefly to wake the polling sleep
                    stop_event = getattr(runner, '_stop_event', None)
                    if stop_event and hasattr(stop_event, 'set'):
                        # Don't actually stop — just interrupt the sleep
                        # The runner checks _stop_event.is_set() and if True, exits.
                        # So we use a different approach: look for a wake event
                        wake_event = getattr(runner, '_wake_event', None)
                        if wake_event and hasattr(wake_event, 'set'):
                            wake_event.set()
                            nudged += 1

                except Exception as e:
                    logger.debug(f"[WakeRecovery] Step 3: nudge error for agent: {e}")

            logger.info(f"[WakeRecovery] Step 3: Nudged {nudged} task runners")
        except Exception as e:
            logger.error(f"[WakeRecovery] Step 3 error: {e}")

    # ------------------------------------------------------------------
    # Step 4: Re-acquire sleep inhibitor if tasks are still active
    # ------------------------------------------------------------------

    def _step_reacquire_sleep_inhibitor(self) -> None:
        """If tasks were running before sleep, re-acquire the sleep inhibitor."""
        try:
            from utils.sleep_inhibitor import get_sleep_inhibitor
            inhibitor = get_sleep_inhibitor()

            # Check if any agent has active tasks
            mw = self._mainwin
            agents = getattr(mw, 'agents', [])
            has_active = False
            for agent in agents:
                active = getattr(agent, 'active_tasks', {})
                if active:
                    has_active = True
                    break

            if has_active and not inhibitor.is_active:
                inhibitor.acquire()
                logger.info("[WakeRecovery] Step 4: Re-acquired sleep inhibitor (tasks still active)")
            elif not has_active:
                logger.info("[WakeRecovery] Step 4: No active tasks — sleep inhibitor not needed")
            else:
                logger.info("[WakeRecovery] Step 4: Sleep inhibitor already active")
        except Exception as e:
            logger.error(f"[WakeRecovery] Step 4 error: {e}")
