"""
Member, group and grant administration for a tenant.

Guard rails: a tenant always keeps at least one active owner; only owners can
create or demote owners; principals are validated before a grant is stored.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from knowledge.ks.authz import PermissionDenied, ROLE_LEVEL
from knowledge.ks.models import (
    PERMISSIONS, PRINCIPAL_TYPES, ROLES, Grant, Group, GroupMember, KnowledgeBase, Membership, Tenant,
)


def _member(m: Membership) -> Dict[str, Any]:
    return {"id": m.id, "tenant_id": m.tenant_id, "user_id": m.user_id or "", "email": m.email or "",
            "display_name": m.display_name or "", "role": m.role, "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None}


class MemberAdmin:
    def __init__(self, store):
        self.store = store

    # ---- members ---------------------------------------------------------------
    def ensure_owner(self, tenant_id: str, user_id: str, email: str = "", name: str = "") -> Dict[str, Any]:
        with self.store.session(write=True) as s:
            m = s.scalars(select(Membership).where(Membership.tenant_id == tenant_id,
                                                   Membership.user_id == user_id)).first()
            if m is None:
                m = Membership(tenant_id=tenant_id, user_id=user_id, email=(email or user_id).lower(),
                               display_name=name, role="owner", status="active")
                s.add(m)
            s.flush()
            return _member(m)

    def list_members(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.store.session() as s:
            rows = s.scalars(select(Membership).where(Membership.tenant_id == tenant_id)
                             .order_by(Membership.created_at)).all()
            out = []
            for m in rows:
                d = _member(m)
                d["groups"] = list(s.scalars(select(GroupMember.group_id).where(GroupMember.membership_id == m.id)))
                out.append(d)
            return out

    def _owners(self, s, tenant_id: str) -> int:
        return s.scalar(select(func.count(Membership.id)).where(
            Membership.tenant_id == tenant_id, Membership.role == "owner", Membership.status == "active")) or 0

    def save_member(self, tenant_id: str, email: str, role: str = "viewer", status: Optional[str] = None,
                    display_name: str = "", member_id: Optional[str] = None, actor_role: str = "owner") -> Dict[str, Any]:
        email = (email or "").strip().lower()
        if role not in ROLES:
            raise ValueError(f"unknown role {role}")
        if status and status not in ("active", "invited", "disabled"):
            raise ValueError(f"unknown status {status}")
        if role == "owner" and actor_role != "owner":
            raise PermissionDenied("only an owner can make someone an owner")
        with self.store.session(write=True) as s:
            m = s.get(Membership, member_id) if member_id else None
            if m is None and email:
                m = s.scalars(select(Membership).where(Membership.tenant_id == tenant_id,
                                                       Membership.email == email)).first()
            if m is None:
                if "@" not in email:
                    raise ValueError("a valid email is required")
                m = Membership(tenant_id=tenant_id, email=email, role=role, status=status or "invited",
                               display_name=display_name)
                s.add(m)
                s.flush()
                return _member(m)
            if m.tenant_id != tenant_id:
                raise PermissionDenied("member belongs to another tenant")
            if m.role == "owner" and actor_role != "owner":
                raise PermissionDenied("only an owner can change an owner")
            demoting_owner = m.role == "owner" and (role != "owner" or (status and status != "active"))
            if demoting_owner and self._owners(s, tenant_id) <= 1:
                raise ValueError("a tenant needs at least one active owner")
            m.role = role
            if status:
                m.status = status
            if display_name:
                m.display_name = display_name
            s.flush()
            return _member(m)

    def remove_member(self, tenant_id: str, member_id: str, actor_role: str = "owner") -> None:
        with self.store.session(write=True) as s:
            m = s.get(Membership, member_id)
            if not m or m.tenant_id != tenant_id:
                return
            if m.role == "owner":
                if actor_role != "owner":
                    raise PermissionDenied("only an owner can remove an owner")
                if self._owners(s, tenant_id) <= 1:
                    raise ValueError("a tenant needs at least one active owner")
            s.delete(m)

    def set_email_domain(self, tenant_id: str, domain: str) -> None:
        with self.store.session(write=True) as s:
            t = s.get(Tenant, tenant_id)
            t.email_domain = (domain or "").strip().lower().lstrip("@")

    # ---- groups ------------------------------------------------------------------
    def list_groups(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.store.session() as s:
            out = []
            for g in s.scalars(select(Group).where(Group.tenant_id == tenant_id).order_by(Group.name)):
                members = list(s.scalars(select(GroupMember.membership_id).where(GroupMember.group_id == g.id)))
                out.append({"id": g.id, "name": g.name, "description": g.description or "", "member_ids": members})
            return out

    def save_group(self, tenant_id: str, name: str, member_ids: List[str], description: str = "",
                   group_id: Optional[str] = None) -> Dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("group name is required")
        with self.store.session(write=True) as s:
            g = s.get(Group, group_id) if group_id else None
            if g is None:
                g = Group(tenant_id=tenant_id, name=name)
                s.add(g)
            elif g.tenant_id != tenant_id:
                raise PermissionDenied("group belongs to another tenant")
            g.name, g.description = name, description
            s.flush()
            valid = set(s.scalars(select(Membership.id).where(Membership.tenant_id == tenant_id,
                                                              Membership.id.in_(member_ids or []))))
            for gm in s.scalars(select(GroupMember).where(GroupMember.group_id == g.id)):
                if gm.membership_id not in valid:
                    s.delete(gm)
            have = set(s.scalars(select(GroupMember.membership_id).where(GroupMember.group_id == g.id)))
            for mid in valid - have:
                s.add(GroupMember(group_id=g.id, membership_id=mid))
            return {"id": g.id, "name": g.name, "description": g.description, "member_ids": sorted(valid)}

    def delete_group(self, tenant_id: str, group_id: str) -> None:
        with self.store.session(write=True) as s:
            g = s.get(Group, group_id)
            if g and g.tenant_id == tenant_id:
                s.query(Grant).filter(Grant.principal_type == "group", Grant.principal_id == group_id).delete()
                s.delete(g)

    # ---- grants --------------------------------------------------------------------
    def list_grants(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.store.session() as s:
            kb_ids = list(s.scalars(select(KnowledgeBase.id).where(KnowledgeBase.tenant_id == tenant_id)))
            return [{"id": g.id, "kb_id": g.kb_id, "principal_type": g.principal_type,
                     "principal_id": g.principal_id, "permission": g.permission}
                    for g in s.scalars(select(Grant).where(Grant.kb_id.in_(kb_ids)))]

    def set_grant(self, tenant_id: str, kb_id: str, principal_type: str, principal_id: str,
                  permission: str) -> Dict[str, Any]:
        if principal_type not in PRINCIPAL_TYPES:
            raise ValueError(f"unknown principal type {principal_type}")
        if permission not in PERMISSIONS:
            raise ValueError(f"unknown permission {permission}")
        principal_id = (principal_id or "").strip()
        if not principal_id:
            raise ValueError("principal is required")
        with self.store.session(write=True) as s:
            kb = s.get(KnowledgeBase, kb_id)
            if not kb or kb.tenant_id != tenant_id:
                raise PermissionDenied("knowledge base belongs to another tenant")
            if principal_type == "group":
                g = s.get(Group, principal_id)
                if not g or g.tenant_id != tenant_id:
                    raise ValueError("unknown group")
            if principal_type == "user":
                principal_id = principal_id.lower() if "@" in principal_id else principal_id
            row = s.scalars(select(Grant).where(Grant.kb_id == kb_id, Grant.principal_type == principal_type,
                                                Grant.principal_id == principal_id)).first()
            if row is None:
                row = Grant(kb_id=kb_id, principal_type=principal_type, principal_id=principal_id)
                s.add(row)
            row.permission = permission
            s.flush()
            return {"id": row.id, "kb_id": kb_id, "principal_type": principal_type,
                    "principal_id": principal_id, "permission": permission}

    def remove_grant(self, tenant_id: str, grant_id: str) -> None:
        with self.store.session(write=True) as s:
            g = s.get(Grant, grant_id)
            if g:
                kb = s.get(KnowledgeBase, g.kb_id)
                if kb and kb.tenant_id == tenant_id:
                    s.delete(g)


__all__ = ["MemberAdmin", "ROLE_LEVEL"]
