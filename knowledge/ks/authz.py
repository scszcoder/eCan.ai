"""
Authorisation for the Knowledge Service: what a principal may do.

Rules (docs/RAG_ENTERPRISE_PLAN.md §2.3):
- Tenant role:   owner/admin -> manage every KB of the tenant
                 editor      -> write non-confidential KBs
                 viewer      -> read non-confidential KBs
- Explicit grants (user / group / agent / store) add read, write or manage on
  one KB, including confidential ones.
- Disabled or non-members get nothing, whatever the grants say.
- An agent acting for a person gets the person's rights; an agent or store
  can also hold its own grants (e.g. a store's customer-service agent reads
  that merchant's catalog).
Every KB a principal may read is a hard partition in retrieval: chunks of
other KBs are never scored.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlalchemy import select

from knowledge.ks.identity import Principal
from knowledge.ks.models import Grant, Group, GroupMember, KnowledgeBase, Membership

LEVEL = {"read": 1, "write": 2, "manage": 3}
ROLE_LEVEL = {"owner": 3, "admin": 3, "editor": 2, "viewer": 1}


class PermissionDenied(Exception):
    pass


class Authorizer:
    def __init__(self, store):
        self.store = store  # KSStore

    # ---- membership ----------------------------------------------------------
    def membership(self, principal: Principal, tenant_id: str) -> Optional[Membership]:
        with self.store.session() as s:
            q = select(Membership).where(Membership.tenant_id == tenant_id)
            rows = s.scalars(q.where(Membership.user_id == principal.user_id)).all()
            if not rows and principal.verified_email:
                rows = s.scalars(q.where(Membership.email == principal.verified_email,
                                         Membership.user_id.in_(["", principal.user_id]))).all()
            m = rows[0] if rows else None
            if m is not None and m.status == "active":
                return m
            return None

    def link_user(self, principal: Principal, tenant_id: str) -> Optional[Dict]:
        """On first sign-in, bind an invited email to the provider subject, or
        auto-join a tenant whose verified email domain matches."""
        from knowledge.ks.models import Tenant
        with self.store.session(write=True) as s:
            q = select(Membership).where(Membership.tenant_id == tenant_id)
            m = s.scalars(q.where(Membership.user_id == principal.user_id)).first()
            if m is None and principal.verified_email:
                # An invite binds once: a row already linked to another account stays theirs.
                m = s.scalars(q.where(Membership.email == principal.verified_email,
                                      Membership.user_id.in_(["", principal.user_id]))).first()
            if m is None:
                t = s.get(Tenant, tenant_id)
                exists = principal.verified_email and s.scalars(
                    q.where(Membership.email == principal.verified_email)).first()
                if t and t.email_domain and principal.domain == t.email_domain.lower() and not exists:
                    m = Membership(tenant_id=tenant_id, email=principal.verified_email, role="viewer", status="active")
                    s.add(m)
                else:
                    return None
            if not m.user_id:
                m.user_id = principal.user_id
            if m.status == "invited":
                m.status = "active"
            if principal.name and not m.display_name:
                m.display_name = principal.name
            s.flush()
            return {"id": m.id, "role": m.role, "status": m.status}

    def group_ids(self, membership_id: str) -> Set[str]:
        with self.store.session() as s:
            return set(s.scalars(select(GroupMember.group_id).where(GroupMember.membership_id == membership_id)))

    # ---- KB permissions ------------------------------------------------------------
    def kb_levels(self, principal: Principal, tenant_id: str) -> Dict[str, int]:
        """kb_id -> highest permission level for this principal in the tenant."""
        m = self.membership(principal, tenant_id)
        levels: Dict[str, int] = {}
        with self.store.session() as s:
            kbs = s.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id == tenant_id)).all()
            role_level = ROLE_LEVEL.get(m.role, 0) if m else 0
            for kb in kbs:
                lvl = 0
                if m:
                    if role_level >= 3:
                        lvl = 3
                    elif kb.sensitivity != "confidential":
                        lvl = role_level
                levels[kb.id] = lvl
            # Every grant needs an active membership in this tenant. The agent and
            # store a request names come from client headers, so they only add a
            # member's own store/agent grants; they never let a non-member in.
            principals = []
            if m:
                principals.append(("user", principal.user_id))
                if principal.verified_email:
                    principals.append(("user", principal.verified_email))
                principals += [("group", g) for g in self.group_ids(m.id)]
                if principal.agent_id:
                    principals.append(("agent", principal.agent_id))
                if principal.store_id:
                    principals.append(("store", principal.store_id))
                for g in s.scalars(select(Grant).where(Grant.kb_id.in_(list(levels)))):
                    if (g.principal_type, g.principal_id) in principals:
                        levels[g.kb_id] = max(levels[g.kb_id], LEVEL.get(g.permission, 0))
        return levels

    def readable_kbs(self, principal: Principal, tenant_id: str) -> Set[str]:
        return {kb for kb, lvl in self.kb_levels(principal, tenant_id).items() if lvl >= 1}

    def require_kb(self, principal: Principal, tenant_id: str, kb_id: str, permission: str) -> None:
        lvl = self.kb_levels(principal, tenant_id).get(kb_id, 0)
        if lvl < LEVEL[permission]:
            raise PermissionDenied(f"{principal.user_id} may not {permission} knowledge base {kb_id}")

    def require_role(self, principal: Principal, tenant_id: str, minimum: str) -> Membership:
        m = self.membership(principal, tenant_id)
        if not m or ROLE_LEVEL.get(m.role, 0) < ROLE_LEVEL[minimum]:
            raise PermissionDenied(f"{principal.user_id} needs the {minimum} role in this tenant")
        return m

    def tenants_for(self, principal: Principal) -> List[str]:
        with self.store.session() as s:
            q = select(Membership.tenant_id).where(Membership.status == "active")
            ids = set(s.scalars(q.where(Membership.user_id == principal.user_id)))
            if principal.verified_email:
                ids |= set(s.scalars(q.where(Membership.email == principal.verified_email,
                                             Membership.user_id.in_(["", principal.user_id]))))
            return sorted(ids)
