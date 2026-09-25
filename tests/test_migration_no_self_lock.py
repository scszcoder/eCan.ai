"""A migration that adds a table must not wait on its own write lock.

2026-09-25 customer (98w, 3.1.6 -> 3.1.8): the missing-table repair ran on a
second connection while the migration session held SQLite's write lock, so
each step waited out the 60s busy timeout. Two steps = a two-minute frozen
startup; the app was closed before the version was saved, and every start
repeated it. Reproduced at 130.9s before the fix.
"""

import os
import tempfile
import time
import unittest

from sqlalchemy import inspect, text


class MigrationSelfLockTests(unittest.TestCase):
    def test_upgrade_that_adds_a_table_is_fast_and_completes(self):
        from agent.db.core.base import get_engine
        from agent.db.migrations.migration_manager import MigrationManager
        from agent.db.models import Base, DBVersion

        engine = get_engine(os.path.join(tempfile.mkdtemp(), "ecan_base.db"))
        Base.metadata.create_all(engine)
        with engine.begin() as c:
            c.execute(text("DROP TABLE store"))
        mm = MigrationManager(engine)
        s = mm.Session()
        DBVersion.upgrade_version(s, "3.1.6", description="as the customer had it")
        s.commit()
        s.close()

        t0 = time.time()
        self.assertTrue(mm.migrate_to_latest())
        self.assertLess(time.time() - t0, 15, "waited on its own lock")
        self.assertIn("store", inspect(engine).get_table_names())
        self.assertEqual(mm.get_current_version(), mm._get_latest_version())


if __name__ == "__main__":
    unittest.main()
