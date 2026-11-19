"""work_status.json: a run's to-do list and what was done per order, so a rerun after an
interruption neither repeats nor skips work (agent/ec_skills/label_utils/work_status.py)."""
from agent.ec_skills.label_utils import work_status as ws

STEPS = ["labels", "file_print", "report", "email"]


def test_a_run_starts_with_every_step_to_do_and_finishes_when_none_is_left(tmp_path):
    d = str(tmp_path)
    ws.start_run(d, "shop1", STEPS)
    assert {s: v["status"] for s, v in ws.load(d)["steps"].items()} == dict.fromkeys(STEPS, "todo")
    for s in STEPS[:-1]:
        ws.mark_step(d, s, "done")
    assert ws.load(d)["runs"][-1]["finished"] is None
    ws.mark_step(d, "email", "done", to="owner@example.com")
    data = ws.load(d)
    assert data["runs"][-1]["finished"] and data["steps"]["email"]["to"] == "owner@example.com"


def test_a_rerun_keeps_what_was_done_to_orders(tmp_path):
    d = str(tmp_path)
    ws.start_run(d, "shop1", STEPS)
    ws.update_order(d, "#1001", status="purchased", total="$7.98", tracking_number="9400")
    ws.update_order(d, "#1001", file="C:/x/1001.pdf", printed=True)
    ws.start_run(d, "shop1", STEPS)                       # interrupted, run again
    o = ws.order(d, "#1001")
    assert o["status"] == "purchased" and o["printed"] is True and o["file"].endswith("1001.pdf")
    assert ws.load(d)["steps"]["labels"]["status"] == "todo" and len(ws.load(d)["runs"]) == 2
    ws.update_order(d, "#1001", tracking_number="")        # an empty value does not erase
    assert ws.order(d, "#1001")["tracking_number"] == "9400"
