"""`ecan skills get/update/remove` resolve an id or a name through skill_service.query_skills."""
from types import SimpleNamespace

import pytest

from cli.skills.commands import _resolve_skill


class _Skills:
    rows = [{"id": "s1", "name": "抖店商品导出"}, {"id": "s2", "name": "other"}]

    def query_skills(self, id=None, name=None):
        if id:
            return {"data": [r for r in self.rows if r["id"] == id]}
        return {"data": [r for r in self.rows if name in r["name"]]}


class _Out:
    def error(self, msg):
        self.msg = msg


def _ctx():
    return SimpleNamespace(db=SimpleNamespace(skill_service=_Skills()))


def test_resolves_by_id_and_by_name():
    assert _resolve_skill(_ctx(), _Out(), "s2") == "s2"
    assert _resolve_skill(_ctx(), _Out(), "抖店商品导出") == "s1"


def test_unknown_skill_exits():
    out = _Out()
    with pytest.raises(SystemExit):
        _resolve_skill(_ctx(), out, "nope")
    assert "nope" in out.msg
