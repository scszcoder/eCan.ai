"""Store Model — a seller's shop as a first-class record.

Until now a store existed only as the ``task_vars.store_id`` string on the
tasks serving it, plus a row in the cloud registry. That made it impossible to
define a store before deploying to it, and left nowhere to keep what belongs to
the store rather than to any one task: its name, platform, URLs and login.

``store_id`` is the same string that task_vars, the usage-event log, token
usage and the cloud registry already key on, so this table joins all of them
without a translation step. It is the local source of truth for a store's
DEFINITION; where it runs (assigned/reported machine, login state) stays in the
cloud registry, which is built for that.

``browser_profile_id`` never leaves the machine: a profile is a live seller
session (see tests/unit/test_browser_profile_stays_local.py).
"""

from sqlalchemy import Column, String, Text, DateTime, Index

from .base_model import BaseModel


class Store(BaseModel):
    """One store (shop) the account operates."""
    __tablename__ = 'store'

    store_id = Column(String, nullable=False, unique=True,
                      comment="Same id task_vars/usage_event/cloud registry use")
    owner = Column(String, nullable=True)
    name = Column(String, nullable=False, default='', comment="Human label")
    platform = Column(String, nullable=False, default='', comment="e.g. douyin, etsy, ebay")
    store_urls = Column(Text, nullable=True, comment="JSON list of the store's workstation/admin URLs")
    browser_profile_id = Column(String, nullable=True, comment="Local-only login profile")
    status = Column(String, nullable=False, default='active', comment="active | archived")
    source = Column(String, nullable=False, default='ui', comment="ui | seed_tasks | seed_cloud")
    cloud_synced_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_store_status', 'status'),
    )

    def __repr__(self):
        return f"<Store(store_id='{self.store_id}', name='{self.name}', platform='{self.platform}')>"
