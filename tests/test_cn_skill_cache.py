"""A serving pod stops re-fetching the same skill on every turn.

Measured on a warm pod, claim -> first LLM call was ~2.8s, of which ~0.8s was
re-fetching the task record and its skill from CloudBase and re-materialising
the skill folder — work that is identical on every turn of the same task, plus
two network round trips that can fail.

Cached per (owner, task_id) with a TTL. The TTL is the whole staleness story:
there is no invalidation signal from the backend, and a customer who edits a
skill expects the pod to notice, so the window is short rather than clever.

The compiled graph is deliberately NOT cached — sharing one across turns would
share whatever its nodes captured, and a wrong answer delivered to the wrong
visitor is worse than a slow one.
"""

import time
from pathlib import Path

import pytest

import agent.cloud_worker.cn_worker_main as cw


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    cw._skill_cache.clear()
    monkeypatch.delenv("ECAN_SKILL_CACHE_TTL", raising=False)
    yield
    cw._skill_cache.clear()


def _entry(tmp_path, name="s", fetched_at=None):
    root = tmp_path / name
    root.mkdir(exist_ok=True)
    e = cw._CachedSkill({"id": "task_1"}, {"id": "skill_1"}, root, root)
    if fetched_at is not None:
        e.fetched_at = fetched_at
    return e


def test_a_fresh_entry_is_returned(tmp_path):
    cw._skill_cache_put("k", _entry(tmp_path))

    got = cw._skill_cache_get("k")

    assert got is not None
    assert got.skill == {"id": "skill_1"}


def test_an_expired_entry_is_dropped(tmp_path):
    """A skill edited in the desktop app has to reach the pod."""
    cw._skill_cache_put("k", _entry(tmp_path, fetched_at=time.time() - 10_000))

    assert cw._skill_cache_get("k") is None
    assert "k" not in cw._skill_cache


def test_a_vanished_folder_is_not_reused(tmp_path):
    """/tmp is swept by the OS; the record can outlive the files."""
    entry = _entry(tmp_path)
    cw._skill_cache_put("k", entry)
    import shutil
    shutil.rmtree(entry.skill_root)

    assert cw._skill_cache_get("k") is None


def test_the_cache_can_be_turned_off(tmp_path, monkeypatch):
    """An escape hatch that does not need a redeploy to use."""
    monkeypatch.setenv("ECAN_SKILL_CACHE_TTL", "0")
    cw._skill_cache_put("k", _entry(tmp_path))

    assert cw._skill_cache_get("k") is None


def test_a_bad_ttl_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("ECAN_SKILL_CACHE_TTL", "not-a-number")

    assert cw._skill_cache_ttl() == 300.0


def test_replacing_an_entry_sweeps_the_old_folder(tmp_path):
    """Otherwise a long-lived pod leaks a skill folder per refresh."""
    old = _entry(tmp_path, name="old")
    new = _entry(tmp_path, name="new")
    cw._skill_cache_put("k", old)
    cw._skill_cache_put("k", new)

    assert not Path(old.work_dir).exists(), "the replaced folder should be gone"
    assert Path(new.work_dir).exists()


def test_replacing_with_the_same_folder_does_not_delete_it(tmp_path):
    """Re-caching the same path must not sweep the path it just stored."""
    entry = _entry(tmp_path)
    cw._skill_cache_put("k", entry)
    again = cw._CachedSkill(entry.task, entry.skill, entry.skill_root, entry.work_dir)
    cw._skill_cache_put("k", again)

    assert Path(entry.work_dir).exists()


def test_the_turn_does_not_delete_a_folder_the_cache_owns(tmp_path):
    """run_single_cn's finally block asks this before rmtree."""
    entry = _entry(tmp_path)
    cw._skill_cache_put("k", entry)

    assert cw._skill_cache_holds("k", entry.work_dir) is True


def test_an_uncached_folder_is_still_swept(tmp_path):
    """The pre-existing behaviour for a turn that did not populate the cache."""
    assert cw._skill_cache_holds("k", tmp_path / "nobody") is False


def test_two_tasks_do_not_share_an_entry(tmp_path):
    """Keyed by owner and task: one customer's skill must not serve another's."""
    a = _entry(tmp_path, name="a")
    b = _entry(tmp_path, name="b")
    b.skill = {"id": "skill_2"}
    cw._skill_cache_put("owner1/task_1", a)
    cw._skill_cache_put("owner2/task_2", b)

    assert cw._skill_cache_get("owner1/task_1").skill == {"id": "skill_1"}
    assert cw._skill_cache_get("owner2/task_2").skill == {"id": "skill_2"}


def test_run_single_cn_consults_the_cache():
    """If the wiring is dropped, the cache exists and does nothing."""
    import inspect

    src = inspect.getsource(cw.run_single_cn)
    assert "_skill_cache_get" in src, "nothing reads the cache"
    # This one was missing on the first cut: the cache was read and swept but
    # never populated, so it was a no-op that looked implemented.
    assert "_skill_cache_put" in src, "nothing populates the cache"
    assert "_skill_cache_holds" in src, "the finally block must not sweep a cached folder"
