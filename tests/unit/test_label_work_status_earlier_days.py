"""An order filed and printed on an earlier day is known as done, so the next day's run does not print it again."""
from agent.ec_skills.label_utils import work_status as ws


def test_an_order_printed_yesterday_is_found(tmp_path):
    root = str(tmp_path)
    ws.update_order(str(tmp_path / "2026-11-23"), "1000000001", status="purchased", file="a.pdf", printed=True)
    ws.update_order(str(tmp_path / "2026-11-23"), "111", status="over_cap")
    day, entry = ws.handled_before(root, "1000000001", "2026-11-24")
    assert day == "2026-11-23" and entry["file"] == "a.pdf"
    assert ws.handled_before(root, "111", "2026-11-24") is None
    assert ws.handled_recently(root, "2026-11-24") == ["1000000001"]


def test_today_and_old_days_do_not_count(tmp_path):
    root = str(tmp_path)
    ws.update_order(str(tmp_path / "2026-11-24"), "1", printed=True)
    ws.update_order(str(tmp_path / "2026-10-01"), "2", printed=True)
    (tmp_path / "originals").mkdir()
    assert ws.handled_recently(root, "2026-11-24") == []
    assert ws.handled_before(root, "1", "2026-11-24") is None
    assert ws.handled_recently(str(tmp_path / "missing"), "2026-11-24") == []
