"""KB Candidate Model — mined Q&A awaiting merchant approval.

The self-learning miner never writes to the knowledge base directly. It writes
*candidates* here (a clustered question + a proposed answer + the source turns
it came from), emails the merchant, and only when the merchant approves in-app
is the candidate promoted into the KB. ``status`` tracks that gate
(pending -> approved/rejected -> promoted); ``promoted_ref`` records where it
landed in the KB.
"""

from sqlalchemy import Column, String, Text, JSON, Float, Index

from .base_model import BaseModel, ExtensibleMixin


class DBKbCandidate(BaseModel, ExtensibleMixin):
    """One mined Q&A candidate for the KB, pending merchant approval."""
    __tablename__ = 'kb_candidate'

    owner = Column(String(128), nullable=True, comment="Account owner (approver)")
    store_id = Column(String(128), nullable=True)
    product_id = Column(String(64), nullable=True)
    platform = Column(String(32), nullable=True)

    question = Column(Text, nullable=False, default='', comment="Canonical/clustered question")
    answer = Column(Text, nullable=False, default='', comment="Proposed answer for the KB")
    rationale = Column(Text, nullable=True, comment="Why proposed / what gap it fills")
    examples = Column(JSON, nullable=True, comment="Source qa_history ids / sample turns")
    confidence = Column(Float, nullable=True, comment="Miner confidence 0..1")

    # Gate: pending | approved | rejected | promoted.
    status = Column(String(16), nullable=False, default='pending', comment="approval gate state")
    promoted_ref = Column(String(128), nullable=True, comment="KB entry id after promotion")

    __table_args__ = (
        Index('idx_kbc_status', 'status'),
        Index('idx_kbc_owner', 'owner'),
    )

    def __repr__(self):
        return f"<DBKbCandidate(id='{self.id}', status='{self.status}')>"
