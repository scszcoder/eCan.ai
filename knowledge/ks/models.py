"""
SQLAlchemy models for the Knowledge Service.

KS has its own declarative base and database (SQLite file on desktop,
PostgreSQL on servers) so it can be deployed without the agent DB.
JSON columns hold structured product data; embeddings are float32 blobs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Planes a knowledge base can live on (docs/RAG_ENTERPRISE_PLAN.md §2.4).
PLANES = ("local", "private", "public")
PERMISSIONS = ("read", "write", "manage")
PRINCIPAL_TYPES = ("user", "group", "agent", "store")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


class Tenant(Base):
    """A merchant or an enterprise."""
    __tablename__ = "ks_tenant"
    id = Column(String(40), primary_key=True, default=lambda: new_id("tn"))
    name = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False, default="merchant")  # merchant | enterprise
    email_domain = Column(String(200))
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Store(Base):
    """A merchant's store on one platform. Products are shared across stores via Listing."""
    __tablename__ = "ks_store"
    id = Column(String(40), primary_key=True, default=lambda: new_id("st"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    platform = Column(String(40), default="")  # taobao | tmall | douyin | pdd | ...
    platform_store_id = Column(String(120), default="")
    ecan_store_id = Column(String(120), default="", index=True)  # agent DB store_id, when linked
    created_at = Column(DateTime(timezone=True), default=utcnow)


class KnowledgeBase(Base):
    __tablename__ = "ks_kb"
    id = Column(String(40), primary_key=True, default=lambda: new_id("kb"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    kind = Column(String(20), nullable=False, default="catalog")  # catalog | policy | docs
    plane = Column(String(20), nullable=False, default="local")
    sensitivity = Column(String(20), nullable=False, default="internal")  # public | internal | confidential
    index_profile = Column(String(40), nullable=False, default="vector")  # vector | vector+graph | vector+graph+mm
    embedder_id = Column(String(200), default="")  # embedder its chunks were built with
    owner = Column(String(200), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Grant(Base):
    __tablename__ = "ks_grant"
    id = Column(String(40), primary_key=True, default=lambda: new_id("gr"))
    kb_id = Column(String(40), ForeignKey("ks_kb.id", ondelete="CASCADE"), nullable=False, index=True)
    principal_type = Column(String(20), nullable=False)
    principal_id = Column(String(200), nullable=False)
    permission = Column(String(20), nullable=False, default="read")
    __table_args__ = (UniqueConstraint("kb_id", "principal_type", "principal_id", name="uq_grant"),)


class Product(Base):
    """Canonical product record, owned by the merchant (tenant)."""
    __tablename__ = "ks_product"
    id = Column(String(40), primary_key=True, default=lambda: new_id("pr"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    kb_id = Column(String(40), ForeignKey("ks_kb.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(120), nullable=False)  # merchant's product code (货号/款号/商家编码)
    title = Column(String(500), nullable=False)
    category = Column(String(200), default="")
    brand = Column(String(200), default="")
    attributes = Column(JSON, default=dict)      # {"材质": "100%棉", ...}
    variants = Column(JSON, default=list)        # [{"sku": "...", "颜色": "黑", "尺码": "M"}]
    size_chart = Column(JSON, default=dict)      # {"headers": [...], "rows": [[...]]}
    selling_points = Column(JSON, default=list)  # ["...", ...]
    description = Column(Text, default="")
    care = Column(Text, default="")
    faq = Column(JSON, default=list)             # [{"q": "...", "a": "..."}]
    images = Column(JSON, default=list)
    source = Column(String(40), default="")      # import | document | manual
    content_hash = Column(String(64), default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    listings = relationship("Listing", back_populates="product", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_product_code"),)


class Listing(Base):
    """A product listed in one store under the platform's item id (商品ID)."""
    __tablename__ = "ks_listing"
    id = Column(String(40), primary_key=True, default=lambda: new_id("ls"))
    product_id = Column(String(40), ForeignKey("ks_product.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(String(40), ForeignKey("ks_store.id", ondelete="CASCADE"), nullable=False, index=True)
    platform_item_id = Column(String(120), default="", index=True)
    title_override = Column(String(500), default="")
    product = relationship("Product", back_populates="listings")
    __table_args__ = (UniqueConstraint("store_id", "product_id", name="uq_listing"),)


class Policy(Base):
    """Store policy text. store_id NULL = merchant default; a store row overrides it."""
    __tablename__ = "ks_policy"
    id = Column(String(40), primary_key=True, default=lambda: new_id("po"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(String(40), ForeignKey("ks_store.id", ondelete="CASCADE"), nullable=True, index=True)
    topic = Column(String(40), nullable=False)  # shipping | returns | invoice | after_sales | ...
    title = Column(String(200), default="")
    text = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "store_id", "topic", name="uq_policy_scope"),)


class Document(Base):
    """A source file ingested into a KB (product sheet, manual, policy doc)."""
    __tablename__ = "ks_document"
    id = Column(String(40), primary_key=True, default=lambda: new_id("dc"))
    kb_id = Column(String(40), ForeignKey("ks_kb.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(40), nullable=False, index=True)
    product_id = Column(String(40), ForeignKey("ks_product.id", ondelete="CASCADE"), nullable=True, index=True)
    store_id = Column(String(40), nullable=True)
    doc_type = Column(String(40), default="product_doc")
    filename = Column(String(500), default="")
    content_hash = Column(String(64), default="", index=True)
    meta = Column(JSON, default=dict)
    labels = Column(JSON, default=list)
    status = Column(String(20), default="ready")
    error = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Chunk(Base):
    """Retrievable unit with scope metadata and its embedding."""
    __tablename__ = "ks_chunk"
    id = Column(String(40), primary_key=True, default=lambda: new_id("ck"))
    kb_id = Column(String(40), ForeignKey("ks_kb.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(40), nullable=False, index=True)
    product_id = Column(String(40), ForeignKey("ks_product.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(String(40), ForeignKey("ks_document.id", ondelete="CASCADE"), nullable=True, index=True)
    policy_id = Column(String(40), ForeignKey("ks_policy.id", ondelete="CASCADE"), nullable=True, index=True)
    store_id = Column(String(40), nullable=True)
    doc_type = Column(String(40), nullable=False)  # summary | faq | text | size_chart | policy
    category = Column(String(200), default="")
    lang = Column(String(10), default="zh")
    text = Column(Text, nullable=False)
    answer = Column(Text, default="")  # FAQ answer; text holds the question
    embedder_id = Column(String(200), default="")
    embedding = Column(LargeBinary)
    __table_args__ = (Index("ix_chunk_tenant_type", "tenant_id", "doc_type"),)


class Job(Base):
    __tablename__ = "ks_job"
    id = Column(String(40), primary_key=True, default=lambda: new_id("jb"))
    kind = Column(String(40), nullable=False)
    tenant_id = Column(String(40), default="")
    title = Column(String(300), default="")
    status = Column(String(20), nullable=False, default="queued")
    stage = Column(String(60), default="")
    progress = Column(Float, default=0.0)
    done = Column(Integer, default=0)
    total = Column(Integer, default=0)
    message = Column(Text, default="")
    errors = Column(JSON, default=list)
    result = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "ks_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=utcnow, index=True)
    actor = Column(String(200), default="")
    action = Column(String(60), nullable=False)
    target = Column(String(200), default="")
    detail = Column(JSON, default=dict)


ROLES = ("owner", "admin", "editor", "viewer")


class Membership(Base):
    """A person in a tenant. Identity comes from the sign-in provider (Cognito,
    CloudBase, enterprise OIDC); the role here decides what they may do."""
    __tablename__ = "ks_membership"
    id = Column(String(40), primary_key=True, default=lambda: new_id("mb"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(200), default="", index=True)   # provider subject, filled on first sign-in
    email = Column(String(200), default="", index=True)     # lowercase
    display_name = Column(String(200), default="")
    role = Column(String(20), nullable=False, default="viewer")
    status = Column(String(20), nullable=False, default="active")  # active | invited | disabled
    created_at = Column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_member_email"),)


class Group(Base):
    __tablename__ = "ks_group"
    id = Column(String(40), primary_key=True, default=lambda: new_id("gp"))
    tenant_id = Column(String(40), ForeignKey("ks_tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_group_name"),)


class GroupMember(Base):
    __tablename__ = "ks_group_member"
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String(40), ForeignKey("ks_group.id", ondelete="CASCADE"), nullable=False, index=True)
    membership_id = Column(String(40), ForeignKey("ks_membership.id", ondelete="CASCADE"), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("group_id", "membership_id", name="uq_group_member"),)


class IndexVersion(Base):
    """Bumped on every write that changes a tenant's chunks. Each process keeps
    its own in-memory index and rebuilds when the stored version moves, so
    several server instances (cloud functions, replicas) stay consistent."""
    __tablename__ = "ks_index_version"
    tenant_id = Column(String(40), primary_key=True)
    version = Column(Integer, nullable=False, default=0)

