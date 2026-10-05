"""Fast Deploy's department goes under the company root, never beside it.

Operations was created parentless (2026-09-28): it became a second top-level
organization, the Agents page wrapped both roots in a virtual root, and the
company's departments were no longer shown at the top.
"""

from unittest.mock import MagicMock

import cli.deploy.commands as dc


def _ctx(rows):
    ctx = MagicMock()
    ctx.db.org_service.get_all_orgs.return_value = {"success": True, "data": rows}
    ctx.db.org_service.search_orgs.return_value = {"success": True, "data": []}
    ctx.db.org_service.add_org.return_value = {"success": True, "id": "org_new"}
    return ctx


def test_new_department_is_placed_under_the_company_root():
    ctx = _ctx([{"id": "org_root_001", "name": "eCan.ai", "org_type": "company", "parent_id": None},
                {"id": "org_sales_001", "name": "Sales", "org_type": "department", "parent_id": "org_root_001"}])
    assert dc._ensure_sales_org(ctx, "me", [], name="Operations") == "org_new"
    data = ctx.db.org_service.add_org.call_args.args[0]
    assert data["parent_id"] == "org_root_001" and data["org_type"] == "department"


def test_without_a_company_root_it_is_created_as_before():
    ctx = _ctx([])
    dc._ensure_sales_org(ctx, "me", [], name="Operations")
    assert "parent_id" not in ctx.db.org_service.add_org.call_args.args[0]


def test_an_existing_department_is_reused_untouched():
    ctx = _ctx([])
    ctx.db.org_service.search_orgs.return_value = {"success": True, "data": [{"id": "org_ops", "name": "Operations"}]}
    assert dc._ensure_sales_org(ctx, "me", [], name="Operations") == "org_ops"
    ctx.db.org_service.add_org.assert_not_called()
