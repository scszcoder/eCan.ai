"""
Usage Event Model — billable business outcomes.

Where ``token_usage`` records what a call COST us, this records what the
customer got: one delivered customer-service reply, one shipping label printed,
one return handled. Billing on outcomes rather than tokens is what lets an
invoice read like the customer's own business instead of like an LLM bill.

Shadow mode (2026-09-21): rows are written and nothing is charged. The cloud
ledger and the rating job are separate work; until they exist this table is a
local record used to find out what a reply actually costs before any price is
committed to.

The row shape deliberately matches the cloud schema field-for-field so the
reporting call is a serialisation, not a translation.

``idempotency_key`` is the heart of it. A turn can be delivered once but
observed several times — retries, drift recovery, duplicate dispatch — and every
one of those must collapse to a single billable event. The key is derived from
the business identity of the turn (store + conversation + source message), never
from a timestamp or a row id.
"""

from sqlalchemy import Column, String, Integer, DateTime, Text, Index
from datetime import datetime
from .base_model import BaseModel


class UsageEvent(BaseModel):
    """One billable business outcome."""

    __tablename__ = 'usage_event'

    # --- identity -------------------------------------------------------
    # Business identity of the outcome. UNIQUE: re-emitting the same turn is a
    # no-op, which is what makes retries and duplicate dispatch safe to bill.
    idempotency_key = Column(String, nullable=False, unique=True,
                             comment="Business identity of this outcome; re-emit is a no-op")

    # --- what happened --------------------------------------------------
    scenario_code = Column(String, nullable=False, comment="Business scenario, e.g. cs_chat")
    meter_code = Column(String, nullable=False, comment="Countable outcome, e.g. message_replied")
    quantity = Column(Integer, nullable=False, default=1, comment="Units (almost always 1)")

    # --- who / where ----------------------------------------------------
    # store_id resolves through prompt_variable_providers.resolve_store_id, the
    # same helper the per-store settings use. Pricing is per-account; store is a
    # reporting dimension.
    owner = Column(String, nullable=True, comment="Account the outcome is billed to")
    store_id = Column(String, nullable=True, comment="Which shop this served ('' = account-wide)")
    agent_id = Column(String, nullable=True)
    task_id = Column(String, nullable=True)
    skill_id = Column(String, nullable=True)
    vehicle_id = Column(String, nullable=True)

    # --- when -----------------------------------------------------------
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow,
                         comment="When the outcome happened (not when it was recorded)")
    reported_at = Column(DateTime, nullable=True, comment="When it reached the cloud ledger")

    # pending -> rated | rejected | reversed. Everything is 'pending' in shadow
    # mode; nothing transitions until the rating job exists.
    status = Column(String, nullable=False, default='pending')

    # --- evidence -------------------------------------------------------
    # What proves this happened: conversation id, source message id, order id.
    # JSON text rather than columns because it differs per meter.
    evidence = Column(Text, nullable=True, comment="JSON: proof of the outcome")
    # What it cost US — tokens and model. Kept per event because the fair-use
    # guard and every margin question compare price against this, so it must be
    # TRUE cost and must never carry a markup.
    cost_basis = Column(Text, nullable=True, comment="JSON: tokens/model consumed")

    source = Column(String, nullable=False, default='client',
                    comment="client | proxy | backend")

    __table_args__ = (
        Index('idx_usage_event_occurred', 'occurred_at'),
        Index('idx_usage_event_owner', 'owner'),
        Index('idx_usage_event_meter', 'scenario_code', 'meter_code'),
        Index('idx_usage_event_status', 'status'),
        Index('idx_usage_event_store', 'store_id'),
    )

    def __repr__(self):
        return (f"<UsageEvent(id='{self.id}', {self.scenario_code}.{self.meter_code}"
                f" x{self.quantity}, store='{self.store_id}', status='{self.status}')>")
