"""A failed task run is re-run only for genuine service errors (KEN 2026-10-30:
the digits "429" inside a draft id re-ran a whole 150-step listing)."""
from agent.ec_tasks.runner import is_retryable_error_text as retry


def test_service_errors_retry():
    assert retry("Error code: 503 - service unavailable")
    assert retry("openai.RateLimitError: Error code: 429")
    assert retry("502 Bad Gateway")


def test_digits_inside_an_id_are_not_a_status_code():
    assert not retry('RuntimeError: no product id: {"draft_id": "3851097162242982376"}')


def test_a_node_marked_non_retryable_is_not_retried():
    assert not retry("[NON_RETRYABLE]listing failed: Error code: 503")


def test_timeouts_are_not_retried():
    assert not retry("TimeoutError: the request timed out")
