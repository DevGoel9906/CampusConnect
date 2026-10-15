"""Communities routes"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from slugify import slugify

from core.database import get_db
from core.security import get_token_payload, get_optional_token_payload
from core.errors import not_found, forbidden, conflict, bad_request
from models.models import (
    Community, CommunityMembership, CommunityStatus, CommunityVisibility,
    MembershipStatus, MembershipRole, Notification, NotificationType
)
from models.schemas import (
    CommunityBody, CommunityUpdateBody, MemberRoleUpdateBody, MembershipReviewBody, PaginationParams
)

router = APIRouter(prefix="/api/communities", tags=["communities"])


async def _assert_community_admin(community_id: str, user_id: str, db: AsyncSession):
    membership = await db.scalar(
        select(CommunityMembership).where(
            and_(CommunityMembership.user_id == user_id,
                 CommunityMembership.community_id == community_id)
        )
    )
    if not membership or membership.status != MembershipStatus.ACTIVE or membership.role not in (MembershipRole.OWNER, MembershipRole.ADMIN):
        raise forbidden("You must be a community admin to do this")
    return membership


@router.get("")
async def list_communities(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    filters = [Community.status == CommunityStatus.ACTIVE, Community.visibility == CommunityVisibility.PUBLIC]
    if q:
        filters.append(Community.name.ilike(f"%{q}%"))
    if category:
        filters.append(Community.category == category)

    rows = await db.execute(
        select(Community).where(and_(*filters)).order_by(Community.created_at.desc()).offset(skip).limit(limit)
    )
    communities = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(Community).where(and_(*filters)))

    return {"success": True, "data": {"communities": [
        {"id": c.id, "slug": c.slug, "name": c.name, "description": c.description,
         "category": c.category, "logoUrl": c.logo_url, "visibility": c.visibility.value}
        for c in communities
    ], "total": total, "page": page, "limit": limit}}


@router.get("/{slug_or_id}")
async def get_community(
    slug_or_id: str,
    payload: Optional[dict] = Depends(get_optional_token_payload),
    db: AsyncSession = Depends(get_db),
):
    community = await db.scalar(select(Community).where(Community.slug == slug_or_id))
    if not community:
        raise not_found("Community")
    if community.status != CommunityStatus.ACTIVE:
        raise not_found("Community")
    if community.visibility == CommunityVisibility.PRIVATE and (not payload or payload.get("role") != "ADMIN"):
        if payload:
            m = await db.scalar(select(CommunityMembership).where(
                and_(CommunityMembership.community_id == community.id,
                     CommunityMembership.user_id == payload["userId"],
                     CommunityMembership.status == MembershipStatus.ACTIVE)
            ))
            if not m:
                raise not_found("Community")
        else:
            raise not_found("Community")

    return {"success": True, "data": {"community": {
        "id": community.id, "slug": community.slug, "name": community.name,
        "description": community.description, "category": community.category,
        "logoUrl": community.logo_url, "visibility": community.visibility.value,
        "status": community.status.value, "objectives": community.objectives,
        "rules": community.rules, "websiteUrl": community.website_url,
    }}}


@router.post("", status_code=201)
async def create_community(body: CommunityBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    base_slug = slugify(body.name)
    slug = base_slug
    attempt = 0
    while await db.scalar(select(Community).where(Community.slug == slug)):
        attempt += 1
        slug = f"{base_slug}-{attempt}"

    community_id = str(uuid.uuid4())
    community = Community(
        id=community_id, slug=slug, name=body.name, description=body.description,
        category=body.category, objectives=body.objectives, rules=body.rules,
        visibility=body.visibility or CommunityVisibility.PUBLIC,
        website_url=body.website_url, owner_id=payload["userId"],
    )
    db.add(community)
    membership = CommunityMembership(
        id=str(uuid.uuid4()), user_id=payload["userId"], community_id=community_id,
        role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(membership)
    await db.commit()
    return {"success": True, "data": {"community": {"id": community.id, "slug": community.slug, "name": community.name}}}


@router.put("/{community_id}")
async def update_community(community_id: str, body: CommunityUpdateBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if payload["role"] != "ADMIN":
        await _assert_community_admin(community_id, payload["userId"], db)
    community = await db.scalar(select(Community).where(Community.id == community_id))
    if not community:
        raise not_found("Community")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(community, field, value)
    await db.commit()
    return {"success": True, "data": {"community": {"id": community.id, "name": community.name}}}


@router.delete("/{community_id}")
async def delete_community(community_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    community = await db.scalar(select(Community).where(Community.id == community_id))
    if not community:
        raise not_found("Community")
    if payload["role"] != "ADMIN":
        await _assert_community_admin(community_id, payload["userId"], db)
    community.status = CommunityStatus.ARCHIVED
    await db.commit()
    return {"success": True, "data": {"community": {"id": community.id, "status": community.status.value}}}


@router.post("/{community_id}/join", status_code=201)
async def join_community(community_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    community = await db.scalar(select(Community).where(Community.id == community_id))
    if not community:
        raise not_found("Community")
    if community.status != CommunityStatus.ACTIVE:
        raise bad_request("Community is not active")
    existing = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == community_id)
    ))
    if existing:
        raise conflict("You are already a member or have a pending request")
    status = MembershipStatus.ACTIVE if community.visibility == CommunityVisibility.PUBLIC else MembershipStatus.PENDING
    membership = CommunityMembership(
        id=str(uuid.uuid4()), user_id=payload["userId"], community_id=community_id,
        status=status, joined_at=datetime.now(timezone.utc) if status == MembershipStatus.ACTIVE else None,
    )
    db.add(membership)
    await db.commit()
    msg = "Joined successfully" if status == MembershipStatus.ACTIVE else "Request sent for approval"
    return {"success": True, "data": {"message": msg}}


@router.delete("/{community_id}/leave")
async def leave_community(community_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    membership = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == community_id)
    ))
    if not membership:
        raise not_found("Membership")
    if membership.role == MembershipRole.OWNER:
        raise bad_request("Owners cannot leave. Transfer ownership first.")
    await db.delete(membership)
    await db.commit()
    return {"success": True, "message": "Left community successfully"}


@router.get("/{community_id}/members")
async def list_members(community_id: str, payload: Optional[dict] = Depends(get_optional_token_payload), db: AsyncSession = Depends(get_db)):
    community = await db.scalar(select(Community).where(Community.id == community_id))
    if not community:
        raise not_found("Community")
    if community.visibility == CommunityVisibility.PRIVATE and (not payload or payload.get("role") != "ADMIN"):
        if payload:
            m = await db.scalar(select(CommunityMembership).where(
                and_(CommunityMembership.community_id == community_id,
                     CommunityMembership.user_id == payload["userId"],
                     CommunityMembership.status == MembershipStatus.ACTIVE)
            ))
            if not m:
                raise not_found("Community")
        else:
            raise not_found("Community")
    rows = await db.execute(select(CommunityMembership).where(
        and_(CommunityMembership.community_id == community_id, CommunityMembership.status == MembershipStatus.ACTIVE)
    ))
    members = rows.scalars().all()
    return {"success": True, "data": {"members": [
        {"userId": m.user_id, "role": m.role.value, "joinedAt": m.joined_at.isoformat() if m.joined_at else None}
        for m in members
    ]}}


@router.patch("/{community_id}/members/{user_id}")
async def update_member(community_id: str, user_id: str, body: MemberRoleUpdateBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    actor = None if payload["role"] == "ADMIN" else await _assert_community_admin(community_id, payload["userId"], db)
    target = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == user_id, CommunityMembership.community_id == community_id)
    ))
    if not target:
        raise not_found("Membership")
    if target.role == MembershipRole.OWNER:
        raise bad_request("Community ownership cannot be changed here")
    target.role = body.role
    await db.commit()
    return {"success": True, "data": {"membership": {"userId": target.user_id, "role": target.role.value}}}


@router.delete("/{community_id}/members/{user_id}")
async def remove_member(community_id: str, user_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if payload["role"] != "ADMIN":
        await _assert_community_admin(community_id, payload["userId"], db)
    target = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == user_id, CommunityMembership.community_id == community_id)
    ))
    if not target:
        raise not_found("Membership")
    if target.role == MembershipRole.OWNER:
        raise bad_request("Community ownership cannot be removed")
    await db.delete(target)
    await db.commit()
    return {"success": True, "message": "Member removed"}


@router.get("/{community_id}/requests")
async def list_requests(community_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if payload["role"] != "ADMIN":
        await _assert_community_admin(community_id, payload["userId"], db)
    rows = await db.execute(select(CommunityMembership).where(
        and_(CommunityMembership.community_id == community_id, CommunityMembership.status == MembershipStatus.PENDING)
    ))
    return {"success": True, "data": {"requests": [
        {"userId": m.user_id, "createdAt": m.created_at.isoformat()}
        for m in rows.scalars().all()
    ]}}


@router.post("/{community_id}/requests/{user_id}/review")
async def review_request(community_id: str, user_id: str, body: MembershipReviewBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if payload["role"] != "ADMIN":
        await _assert_community_admin(community_id, payload["userId"], db)
    membership = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == user_id, CommunityMembership.community_id == community_id)
    ))
    if not membership or membership.status != MembershipStatus.PENDING:
        raise not_found("Membership request")
    if body.action == "APPROVE":
        membership.status = MembershipStatus.ACTIVE
        membership.joined_at = datetime.now(timezone.utc)
        notif_type = NotificationType.MEMBERSHIP_APPROVED
        notif_title = "Membership approved"
        notif_msg = "Your membership request has been approved"
    else:
        membership.status = MembershipStatus.REJECTED
        notif_type = NotificationType.MEMBERSHIP_REJECTED
        notif_title = "Membership request rejected"
        notif_msg = "Your membership request was not approved"
    notif = Notification(
        id=str(uuid.uuid4()), user_id=user_id,
        type=notif_type, title=notif_title, message=notif_msg,
    )
    db.add(notif)
    await db.commit()
    return {"success": True, "data": {"membership": {"userId": membership.user_id, "status": membership.status.value}}}
