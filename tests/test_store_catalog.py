"""Store catalog: define a store first, then deploy into it."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import create_engine

from agent.db.models.store_model import Store
from agent.db.services.db_store_service import DBStoreService
from agent.ec_agents import store_catalog as sc


def _mainwin(agents=()):
    path = os.path.join(tempfile.mkdtemp(), "stores.db")
    engine = create_engine(f"sqlite:///{path}")
    Store.__table__.create(engine)
    return SimpleNamespace(ec_db_mgr=SimpleNamespace(store_service=DBStoreService(engine=engine)),
                           agents=list(agents))


def _agent(*store_ids):
    return SimpleNamespace(card=SimpleNamespace(id="a", name="a"), _running=False, status="active",
                           tasks=[SimpleNamespace(id=f"t{i}", name="t", metadata={"task_vars": {"store_id": s}})
                                  for i, s in enumerate(store_ids)])


class StoreIdTests(unittest.TestCase):
    def test_the_feige_constant_and_blank_are_refused_like_the_server_does(self):
        self.assertIsNotNone(sc.store_id_problem(""))
        self.assertIsNotNone(sc.store_id_problem("im.jinritemai.com/pc_seller_v2"))
        self.assertIsNotNone(sc.store_id_problem("x" * 129))
        self.assertIsNone(sc.store_id_problem("小店一号"))


class CreateTests(unittest.TestCase):
    def _create(self, mw, data, assign_result=None, assign_exc=None):
        m = mock.Mock(side_effect=assign_exc) if assign_exc else mock.Mock(
            return_value=assign_result or {"store": {}, "warnings": []})
        with mock.patch("agent.cloud_api.store_api.store_assign", m), \
             mock.patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="me"):
            return sc.create_store(mw, data), m

    def test_a_new_store_is_saved_and_defined_in_the_cloud(self):
        mw = _mainwin()
        out, assign = self._create(mw, {"store_id": "shop1", "name": "Shop One", "platform": "douyin",
                                        "store_urls": ["https://a", " ", "https://b"], "assign": "here"})
        self.assertEqual(out["store"]["name"], "Shop One")
        self.assertEqual(out["store"]["store_urls"], ["https://a", "https://b"])
        self.assertEqual(assign.call_args.args, ("shop1", "me"))
        self.assertEqual(assign.call_args.kwargs, {"platform": "douyin", "label": "Shop One"})
        self.assertIsNotNone(out["store"]["cloud_synced_at"])

    def test_unassigned_means_defined_but_left_for_placement_to_claim(self):
        _, assign = self._create(_mainwin(), {"store_id": "s", "assign": "none"})
        self.assertEqual(assign.call_args.args, ("s", None))

    def test_no_cloud_keeps_the_store_locally_with_a_warning(self):
        out, _ = self._create(_mainwin(), {"store_id": "s"}, assign_exc=RuntimeError("signed out"))
        self.assertEqual(out["store"]["store_id"], "s")
        self.assertIsNone(out["store"]["cloud_synced_at"])
        self.assertTrue(any("signed out" in w for w in out["warnings"]))

    def test_duplicates_and_url_ids_are_refused(self):
        mw = _mainwin()
        self._create(mw, {"store_id": "s"})
        with self.assertRaises(ValueError):
            self._create(mw, {"store_id": "s"})
        with self.assertRaises(ValueError):
            self._create(mw, {"store_id": "https://im.jinritemai.com/x"})

    def test_the_chosen_profile_is_tagged_with_the_store(self):
        saved = []
        with mock.patch("agent.ec_skills.browser_use_extension.fingerprint.profile_registry.get_profile",
                        return_value={"id": "p1", "store_id": ""}), \
             mock.patch("agent.ec_skills.browser_use_extension.fingerprint.profile_registry.save_profile",
                        side_effect=lambda p: saved.append(p)):
            out, _ = self._create(_mainwin(), {"store_id": "s", "browser_profile_id": "p1"})
        self.assertEqual(saved[0]["store_id"], "s")
        self.assertEqual(out["store"]["browser_profile_id"], "p1")

    def test_an_unknown_profile_is_refused_before_anything_is_saved(self):
        mw = _mainwin()
        with mock.patch("agent.ec_skills.browser_use_extension.fingerprint.profile_registry.get_profile",
                        return_value=None):
            with self.assertRaises(ValueError):
                self._create(mw, {"store_id": "s", "browser_profile_id": "nope"})
        self.assertIsNone(mw.ec_db_mgr.store_service.get_store("s"))


class SeedTests(unittest.TestCase):
    def test_existing_stores_get_records_and_nothing_is_overwritten(self):
        mw = _mainwin(agents=[_agent("from-task")])
        mw.ec_db_mgr.store_service.upsert_store({"store_id": "mine", "name": "My name"})
        n = sc.seed(mw, cloud_rows=[{"storeId": "mine", "label": "cloud label"},
                                    {"storeId": "from-cloud", "label": "Cloud Shop", "platform": "douyin"}])
        self.assertEqual(n, 2)
        by = {s["store_id"]: s for s in mw.ec_db_mgr.store_service.list_stores()}
        self.assertEqual(by["mine"]["name"], "My name")
        self.assertEqual((by["from-cloud"]["name"], by["from-cloud"]["source"]), ("Cloud Shop", "seed_cloud"))
        self.assertEqual(by["from-task"]["source"], "seed_tasks")
        self.assertEqual(sc.seed(mw), 0, "idempotent")


class UpdateTests(unittest.TestCase):
    def test_fields_change_and_an_unknown_store_is_refused(self):
        mw = _mainwin()
        mw.ec_db_mgr.store_service.upsert_store({"store_id": "s", "name": "old"})
        out = sc.update_store(mw, {"store_id": "s", "name": "new", "store_urls": ["https://c"]})
        self.assertEqual((out["store"]["name"], out["store"]["store_urls"]), ("new", ["https://c"]))
        with self.assertRaises(ValueError):
            sc.update_store(mw, {"store_id": "nope", "name": "x"})


if __name__ == "__main__":
    unittest.main()
