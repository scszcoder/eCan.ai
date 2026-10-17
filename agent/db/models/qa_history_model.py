"""Q&A History Model — resolved customer question/answer turns.

Every time a customer-service agent's answer is confirmed delivered to a
buyer, the turn is appended here: the customer's question, the answer that
actually went out, and the full scope it happened in (store / agent / task /
product / timestamp). The platform live-chat traffic (飞鸽 / 千牛 / 抖店) is
otherwise only in-memory and in runlogs, so this table is the first durable,
queryable record of it.

It is the raw feed for the self-learning KB pipeline: a mining skill reads the
``status='new'`` rows, clusters + dedups them, and proposes candidate KB
entries the merchant approves by email before anything enters the knowledge
base. ``status`` tracks that lifecycle (new -> mined -> promoted / rejected);
nothing is ever auto-published.
"""

from sqlalchemy import Column, String, Text, Index

from .base_model import BaseModel, ExtensibleMixin


class DBQaHistory(BaseModel, ExtensibleMixin):
    """One resolved customer<->agent Q&A turn."""
    __tablename__ = 'qa_history'

    # Scope — the keys the rest of the system already uses.
    store_id = Column(String(128), nullable=True, comment="Serving store (task_vars.store_id)")
    agent_id = Column(String(64), nullable=True, comment="Answering agent")
    task_id = Column(String(64), nullable=True, comment="Serving task")
    product_id = Column(String(64), nullable=True, comment="商品ID in scope, if any")
    platform = Column(String(32), nullable=True, comment="e.g. douyin, qianniu")
    owner = Column(String(128), nullable=True, comment="Account owner (for per-account mining)")

    # Conversation identity.
    customer_id = Column(String(128), nullable=True)
    customer_name = Column(String(255), nullable=True)
    chat_id = Column(String(128), nullable=True, comment="talk_id / chat id")
    source_msg_id = Column(String(128), nullable=True, comment="Inbound customer message id")

    # The turn itself.
    question = Column(Text, nullable=False, default='', comment="Customer's inbound message")
    answer = Column(Text, nullable=False, default='', comment="Answer delivered to the customer")

    # Mining lifecycle: new | mined | promoted | rejected.
    status = Column(String(16), nullable=False, default='new', comment="mining lifecycle state")

    __table_args__ = (
        Index('idx_qa_status', 'status'),
        Index('idx_qa_store', 'store_id'),
    )

    def __repr__(self):
        return (f"<DBQaHistory(id='{self.id}', store='{self.store_id}', "
                f"status='{self.status}')>")
