"""Events, projects, discussions, notifications, users, admin routers"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from passlib.context import CryptContext

from core.database import get_db
from core.security import get_token_payload, get_optional_token_payload
from core.errors import not_found, forbidden, conflict, bad_request
from models.models import (
    Event, EventRegistration, EventStatus,
    Project, ProjectMembership, CollaborationRequest, CollaborationStatus, ProjectStatus,
    Discussion, Comment, Notification, NotificationType,
    User, UserProfile, CommunityMembership, MembershipStatus, MembershipRole,
    Report, ReportStatus, UserRole
)
from models.schemas import (
    EventBody, EventUpdateBody, ProjectBody, ProjectUpdateBody,
    CollaborationRequestBody, CollaborationReviewBody,
    DiscussionBody, CommentBody, UpdateProfileBody,
    UserRoleUpdateBody, ReportStatusBody
)

# ══════════════════════════════════════════════════════════════════════════════
# EVENTS
# ══════════════════════════════════════════════════════════════════════════════

events_router = APIRouter(prefix="/api/events", tags=["events"])


@events_router.get("")
async def list_events(
    q: Optional[str] = None, community_id: Optional[str] = None,
    upcoming: Optional[str] = None,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    filters = [Event.status == EventStatus.PUBLISHED]
    if q:
        filters.append(Event.title.ilike(f"%{q}%"))
    if community_id:
        filters.append(Event.community_id == community_id)
    if upcoming == "true":
        filters.append(Event.start_at >= datetime.now(timezone.utc))
    rows = await db.execute(select(Event).where(and_(*filters)).order_by(Event.start_at.asc()).offset(skip).limit(limit))
    events = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(Event).where(and_(*filters)))
    return {"success": True, "data": {"events": [
        {"id": e.id, "title": e.title, "description": e.description,
         "startAt": e.start_at.isoformat(), "endAt": e.end_at.isoformat(),
         "venue": e.venue, "status": e.status.value, "tags": e.tags}
        for e in events
    ], "total": total, "page": page, "limit": limit}}


@events_router.get("/{event_id}")
async def get_event(event_id: str, payload: Optional[dict] = Depends(get_optional_token_payload), db: AsyncSession = Depends(get_db)):
    event = await db.scalar(select(Event).where(Event.id == event_id))
    if not event:
        raise not_found("Event")
    if event.status != EventStatus.PUBLISHED:
        if not payload or (payload["userId"] != event.creator_id and payload["role"] != "ADMIN"):
            raise not_found("Event")
    reg_count = await db.scalar(select(func.count()).select_from(EventRegistration).where(EventRegistration.event_id == event_id))
    return {"success": True, "data": {"event": {
        "id": event.id, "title": event.title, "description": event.description,
        "startAt": event.start_at.isoformat(), "endAt": event.end_at.isoformat(),
        "venue": event.venue, "meetingLink": event.meeting_link,
        "maxCapacity": event.max_capacity, "status": event.status.value,
        "tags": event.tags, "registrationCount": reg_count,
    }}}


@events_router.post("", status_code=201)
async def create_event(body: EventBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if body.start_at >= body.end_at:
        raise bad_request("Event end time must be after start time")
    if body.community_id:
        membership = await db.scalar(select(CommunityMembership).where(
            and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == body.community_id)
        ))
        if not membership or membership.status != MembershipStatus.ACTIVE or membership.role not in (MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.MODERATOR):
            raise forbidden("You must be a community moderator to create events")
    event = Event(
        id=str(uuid.uuid4()), title=body.title, description=body.description,
        community_id=body.community_id, creator_id=payload["userId"],
        venue=body.venue, meeting_link=body.meeting_link,
        start_at=body.start_at, end_at=body.end_at,
        max_capacity=body.max_capacity, status=body.status or EventStatus.DRAFT,
        tags=body.tags or [],
    )
    db.add(event)
    await db.commit()
    return {"success": True, "data": {"event": {"id": event.id, "title": event.title}}}


@events_router.put("/{event_id}")
async def update_event(event_id: str, body: EventUpdateBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    event = await db.scalar(select(Event).where(Event.id == event_id))
    if not event:
        raise not_found("Event")
    if event.creator_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the event creator can update this event")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(event, field.replace("_at", "_at"), value)
    await db.commit()
    return {"success": True, "data": {"event": {"id": event.id, "title": event.title, "status": event.status.value}}}


@events_router.delete("/{event_id}")
async def delete_event(event_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    event = await db.scalar(select(Event).where(Event.id == event_id))
    if not event:
        raise not_found("Event")
    if event.creator_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the event creator can delete this event")
    event.status = EventStatus.CANCELLED
    await db.commit()
    return {"success": True, "message": "Event cancelled"}


@events_router.post("/{event_id}/register", status_code=201)
async def register_for_event(event_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    event = await db.scalar(select(Event).where(Event.id == event_id))
    if not event:
        raise not_found("Event")
    if event.status != EventStatus.PUBLISHED:
        raise bad_request("Event is not open for registration")
    if event.start_at < datetime.now(timezone.utc):
        raise bad_request("Event has already started")
    if event.max_capacity:
        count = await db.scalar(select(func.count()).select_from(EventRegistration).where(EventRegistration.event_id == event_id))
        if count >= event.max_capacity:
            raise bad_request("Event is at full capacity")
    existing = await db.scalar(select(EventRegistration).where(
        and_(EventRegistration.event_id == event_id, EventRegistration.user_id == payload["userId"])
    ))
    if existing:
        raise conflict("You are already registered for this event")
    reg = EventRegistration(id=str(uuid.uuid4()), event_id=event_id, user_id=payload["userId"])
    notif = Notification(
        id=str(uuid.uuid4()), user_id=payload["userId"],
        type=NotificationType.EVENT_REGISTERED,
        title=f"Registered: {event.title}",
        message=f"You have successfully registered for {event.title}",
    )
    db.add(reg)
    db.add(notif)
    await db.commit()
    return {"success": True, "data": {"registration": {"id": reg.id}}}


@events_router.delete("/{event_id}/register")
async def unregister_from_event(event_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    reg = await db.scalar(select(EventRegistration).where(
        and_(EventRegistration.event_id == event_id, EventRegistration.user_id == payload["userId"])
    ))
    if not reg:
        raise not_found("Registration")
    await db.delete(reg)
    await db.commit()
    return {"success": True, "message": "Unregistered from event"}


# ══════════════════════════════════════════════════════════════════════════════
# PROJECTS
# ══════════════════════════════════════════════════════════════════════════════

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])


@projects_router.get("")
async def list_projects(
    q: Optional[str] = None, category: Optional[str] = None,
    status: Optional[str] = None, technology: Optional[str] = None,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    filters = [Project.status != ProjectStatus.CANCELLED]
    if q:
        filters.append(Project.title.ilike(f"%{q}%"))
    if category:
        filters.append(Project.category == category)
    if status:
        filters.append(Project.status == status)
    rows = await db.execute(select(Project).where(and_(*filters)).order_by(Project.created_at.desc()).offset(skip).limit(limit))
    projects = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(Project).where(and_(*filters)))
    return {"success": True, "data": {"projects": [
        {"id": p.id, "title": p.title, "description": p.description,
         "category": p.category, "status": p.status.value, "techStack": p.tech_stack}
        for p in projects
    ], "total": total, "page": page, "limit": limit}}


@projects_router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise not_found("Project")
    member_count = await db.scalar(select(func.count()).select_from(ProjectMembership).where(ProjectMembership.project_id == project_id))
    return {"success": True, "data": {"project": {
        "id": project.id, "title": project.title, "description": project.description,
        "objectives": project.objectives, "techStack": project.tech_stack,
        "category": project.category, "status": project.status.value,
        "repoUrl": project.repo_url, "demoUrl": project.demo_url,
        "requiredSkills": project.required_skills, "maxTeamSize": project.max_team_size,
        "memberCount": member_count,
    }}}


@projects_router.post("", status_code=201)
async def create_project(body: ProjectBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    if body.community_id:
        membership = await db.scalar(select(CommunityMembership).where(
            and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == body.community_id)
        ))
        if not membership or membership.status != MembershipStatus.ACTIVE:
            raise forbidden("You must be a community member to create a project there")
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id, title=body.title, description=body.description,
        objectives=body.objectives, tech_stack=body.tech_stack or [],
        category=body.category, community_id=body.community_id,
        repo_url=body.repo_url, demo_url=body.demo_url,
        required_skills=body.required_skills or [], max_team_size=body.max_team_size,
        status=body.status or ProjectStatus.IDEA, owner_id=payload["userId"],
    )
    db.add(project)
    pm = ProjectMembership(id=str(uuid.uuid4()), project_id=project_id, user_id=payload["userId"], role=MembershipRole.OWNER)
    db.add(pm)
    await db.commit()
    return {"success": True, "data": {"project": {"id": project.id, "title": project.title}}}


@projects_router.put("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdateBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise not_found("Project")
    if project.owner_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the project owner can update this project")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.commit()
    return {"success": True, "data": {"project": {"id": project.id, "title": project.title}}}


@projects_router.delete("/{project_id}")
async def delete_project(project_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise not_found("Project")
    if project.owner_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the project owner can archive this project")
    project.status = ProjectStatus.CANCELLED
    await db.commit()
    return {"success": True, "message": "Project archived"}


@projects_router.post("/{project_id}/collaborate", status_code=201)
async def request_collaboration(project_id: str, body: CollaborationRequestBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise not_found("Project")
    if project.owner_id == payload["userId"]:
        raise bad_request("You already own this project")
    if project.status in (ProjectStatus.CANCELLED, ProjectStatus.COMPLETED):
        raise bad_request("This project is not accepting collaborators")
    existing_member = await db.scalar(select(ProjectMembership).where(
        and_(ProjectMembership.project_id == project_id, ProjectMembership.user_id == payload["userId"])
    ))
    if existing_member:
        raise conflict("You are already a member of this project")
    existing_req = await db.scalar(select(CollaborationRequest).where(
        and_(CollaborationRequest.project_id == project_id,
             CollaborationRequest.sender_id == payload["userId"],
             CollaborationRequest.status == CollaborationStatus.PENDING)
    ))
    if existing_req:
        raise conflict("You already have a pending request")
    req = CollaborationRequest(
        id=str(uuid.uuid4()), project_id=project_id,
        sender_id=payload["userId"], message=body.message,
    )
    notif = Notification(
        id=str(uuid.uuid4()), user_id=project.owner_id,
        type=NotificationType.COLLABORATION_REQUEST,
        title="New collaboration request",
        message=f"Someone wants to join your project: {project.title}",
    )
    db.add(req)
    db.add(notif)
    await db.commit()
    return {"success": True, "data": {"request": {"id": req.id}}}


@projects_router.post("/{project_id}/collaborate/{request_id}/review")
async def review_collaboration(project_id: str, request_id: str, body: CollaborationReviewBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise not_found("Project")
    if project.owner_id != payload["userId"]:
        raise forbidden("Only the project owner can review requests")
    req = await db.scalar(select(CollaborationRequest).where(CollaborationRequest.id == request_id))
    if not req or req.project_id != project_id:
        raise not_found("Request")
    if req.status != CollaborationStatus.PENDING:
        raise bad_request("This collaboration request has already been reviewed")
    if body.action == "ACCEPT":
        req.status = CollaborationStatus.ACCEPTED
        if project.max_team_size:
            count = await db.scalar(select(func.count()).select_from(ProjectMembership).where(ProjectMembership.project_id == project_id))
            if count >= project.max_team_size:
                raise bad_request("This project has reached its maximum team size")
        pm = ProjectMembership(id=str(uuid.uuid4()), project_id=project_id, user_id=req.sender_id)
        db.add(pm)
        notif_type = NotificationType.COLLABORATION_ACCEPTED
        notif_title = "Collaboration request accepted"
        notif_msg = f"You've been added to the project: {project.title}"
    else:
        req.status = CollaborationStatus.REJECTED
        notif_type = NotificationType.COLLABORATION_REJECTED
        notif_title = "Collaboration request rejected"
        notif_msg = f"Your request to join {project.title} was not accepted"
    notif = Notification(id=str(uuid.uuid4()), user_id=req.sender_id, type=notif_type, title=notif_title, message=notif_msg)
    db.add(notif)
    await db.commit()
    return {"success": True, "message": f"Request {body.action.lower()}ed"}


# ══════════════════════════════════════════════════════════════════════════════
# DISCUSSIONS
# ══════════════════════════════════════════════════════════════════════════════

discussions_router = APIRouter(prefix="/api/discussions", tags=["discussions"])


@discussions_router.get("/community/{community_id}")
async def list_discussions(
    community_id: str,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    payload: Optional[dict] = Depends(get_optional_token_payload),
    db: AsyncSession = Depends(get_db),
):
    from models.models import Community, CommunityVisibility
    community = await db.scalar(select(Community).where(Community.id == community_id))
    if not community:
        raise not_found("Community")
    skip = (page - 1) * limit
    rows = await db.execute(
        select(Discussion).where(Discussion.community_id == community_id)
        .order_by(Discussion.is_pinned.desc(), Discussion.created_at.desc())
        .offset(skip).limit(limit)
    )
    discussions = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(Discussion).where(Discussion.community_id == community_id))
    return {"success": True, "data": {"discussions": [
        {"id": d.id, "title": d.title, "body": d.body, "isPinned": d.is_pinned,
         "createdAt": d.created_at.isoformat(), "authorId": d.author_id}
        for d in discussions
    ], "total": total, "page": page, "limit": limit}}


@discussions_router.get("/{discussion_id}")
async def get_discussion(discussion_id: str, payload: Optional[dict] = Depends(get_optional_token_payload), db: AsyncSession = Depends(get_db)):
    discussion = await db.scalar(select(Discussion).where(Discussion.id == discussion_id))
    if not discussion:
        raise not_found("Discussion")
    return {"success": True, "data": {"discussion": {
        "id": discussion.id, "title": discussion.title, "body": discussion.body,
        "isPinned": discussion.is_pinned, "communityId": discussion.community_id,
        "authorId": discussion.author_id, "createdAt": discussion.created_at.isoformat(),
    }}}


@discussions_router.post("/community/{community_id}", status_code=201)
async def create_discussion(community_id: str, body: DiscussionBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    membership = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == community_id)
    ))
    if not membership or membership.status != MembershipStatus.ACTIVE:
        raise forbidden("You must be a member to post in this community")
    discussion = Discussion(
        id=str(uuid.uuid4()), title=body.title, body=body.body,
        community_id=community_id, author_id=payload["userId"],
    )
    db.add(discussion)
    await db.commit()
    return {"success": True, "data": {"discussion": {"id": discussion.id, "title": discussion.title}}}


@discussions_router.put("/{discussion_id}")
async def update_discussion(discussion_id: str, body: DiscussionBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    discussion = await db.scalar(select(Discussion).where(Discussion.id == discussion_id))
    if not discussion:
        raise not_found("Discussion")
    if discussion.author_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the author can edit this discussion")
    discussion.title = body.title
    discussion.body = body.body
    await db.commit()
    return {"success": True, "data": {"discussion": {"id": discussion.id}}}


@discussions_router.delete("/{discussion_id}")
async def delete_discussion(discussion_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    discussion = await db.scalar(select(Discussion).where(Discussion.id == discussion_id))
    if not discussion:
        raise not_found("Discussion")
    if discussion.author_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the author can delete this discussion")
    await db.delete(discussion)
    await db.commit()
    return {"success": True, "message": "Discussion deleted"}


@discussions_router.get("/{discussion_id}/comments")
async def list_comments(discussion_id: str, payload: Optional[dict] = Depends(get_optional_token_payload), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Comment).where(and_(Comment.discussion_id == discussion_id, Comment.parent_id == None))
        .order_by(Comment.created_at.asc())
    )
    comments = rows.scalars().all()
    return {"success": True, "data": {"comments": [
        {"id": c.id, "body": c.body, "authorId": c.author_id, "createdAt": c.created_at.isoformat()}
        for c in comments
    ]}}


@discussions_router.post("/{discussion_id}/comments", status_code=201)
async def add_comment(discussion_id: str, body: CommentBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    discussion = await db.scalar(select(Discussion).where(Discussion.id == discussion_id))
    if not discussion:
        raise not_found("Discussion")
    membership = await db.scalar(select(CommunityMembership).where(
        and_(CommunityMembership.user_id == payload["userId"], CommunityMembership.community_id == discussion.community_id)
    ))
    if not membership or membership.status != MembershipStatus.ACTIVE:
        raise forbidden("You must be a community member to comment")
    comment = Comment(
        id=str(uuid.uuid4()), body=body.body, discussion_id=discussion_id,
        author_id=payload["userId"], parent_id=body.parent_id,
    )
    db.add(comment)
    await db.commit()
    return {"success": True, "data": {"comment": {"id": comment.id}}}


@discussions_router.delete("/{discussion_id}/comments/{comment_id}")
async def delete_comment(discussion_id: str, comment_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    comment = await db.scalar(select(Comment).where(Comment.id == comment_id))
    if not comment:
        raise not_found("Comment")
    if comment.author_id != payload["userId"] and payload["role"] != "ADMIN":
        raise forbidden("Only the author can delete this comment")
    await db.delete(comment)
    await db.commit()
    return {"success": True, "message": "Comment deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

notifications_router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@notifications_router.get("")
async def list_notifications(
    unread_only: Optional[str] = Query(default=None, alias="unreadOnly"),
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    filters = [Notification.user_id == payload["userId"]]
    if unread_only == "true":
        filters.append(Notification.is_read == False)
    rows = await db.execute(select(Notification).where(and_(*filters)).order_by(Notification.created_at.desc()).offset(skip).limit(limit))
    notifications = rows.scalars().all()
    unread = await db.scalar(select(func.count()).select_from(Notification).where(
        and_(Notification.user_id == payload["userId"], Notification.is_read == False)
    ))
    return {"success": True, "data": {"notifications": [
        {"id": n.id, "type": n.type.value, "title": n.title, "message": n.message,
         "isRead": n.is_read, "createdAt": n.created_at.isoformat()}
        for n in notifications
    ], "unreadCount": unread, "page": page, "limit": limit}}


@notifications_router.patch("/{notification_id}/read")
async def mark_read(notification_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    notif = await db.scalar(select(Notification).where(Notification.id == notification_id))
    if not notif:
        raise not_found("Notification")
    if notif.user_id != payload["userId"]:
        raise forbidden()
    notif.is_read = True
    await db.commit()
    return {"success": True}


@notifications_router.patch("/read-all")
async def mark_all_read(payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Notification).where(and_(Notification.user_id == payload["userId"], Notification.is_read == False)))
    for n in rows.scalars().all():
        n.is_read = True
    await db.commit()
    return {"success": True}


@notifications_router.delete("/{notification_id}")
async def delete_notification(notification_id: str, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    notif = await db.scalar(select(Notification).where(Notification.id == notification_id))
    if not notif:
        raise not_found("Notification")
    if notif.user_id != payload["userId"]:
        raise forbidden()
    await db.delete(notif)
    await db.commit()
    return {"success": True}


# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

users_router = APIRouter(prefix="/api/users", tags=["users"])


@users_router.get("")
async def list_users(
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * limit
    rows = await db.execute(select(UserProfile).where(UserProfile.is_public == True).offset(skip).limit(limit))
    profiles = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(UserProfile).where(UserProfile.is_public == True))
    return {"success": True, "data": {"users": [
        {"userId": p.user_id, "displayName": p.display_name, "avatarUrl": p.avatar_url,
         "college": p.college, "skills": p.skills}
        for p in profiles
    ], "total": total, "page": page, "limit": limit}}


@users_router.get("/{user_id}")
async def get_user(user_id: str, payload: Optional[dict] = Depends(get_optional_token_payload), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise not_found("User")
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    if profile and not profile.is_public:
        if not payload or (payload["userId"] != user_id and payload["role"] != "ADMIN"):
            raise not_found("User")
    return {"success": True, "data": {"user": {
        "id": user.id, "role": user.role.value, "createdAt": user.created_at.isoformat(),
        "profile": {"displayName": profile.display_name, "bio": profile.bio,
                    "avatarUrl": profile.avatar_url, "college": profile.college,
                    "skills": profile.skills, "interests": profile.interests,
                    "isPublic": profile.is_public} if profile else None,
    }}}


@users_router.patch("/me/profile")
async def update_profile(body: UpdateProfileBody, payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == payload["userId"]))
    if not profile:
        raise not_found("Profile")
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(profile, field, value or None if "url" in field else value)
    await db.commit()
    return {"success": True, "data": {"profile": {"displayName": profile.display_name, "bio": profile.bio}}}


@users_router.get("/me/dashboard")
async def get_dashboard(payload: dict = Depends(get_token_payload), db: AsyncSession = Depends(get_db)):
    user_id = payload["userId"]
    user = await db.scalar(select(User).where(User.id == user_id))
    profile = await db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
    memberships_rows = await db.execute(
        select(CommunityMembership).where(and_(CommunityMembership.user_id == user_id, CommunityMembership.status == MembershipStatus.ACTIVE)).limit(6)
    )
    notifs_rows = await db.execute(
        select(Notification).where(and_(Notification.user_id == user_id, Notification.is_read == False)).order_by(Notification.created_at.desc()).limit(10)
    )
    return {"success": True, "data": {
        "user": {"id": user.id, "email": user.email, "role": user.role.value,
                 "profile": {"displayName": profile.display_name} if profile else None},
        "memberships": [{"communityId": m.community_id} for m in memberships_rows.scalars().all()],
        "notifications": [{"id": n.id, "title": n.title, "isRead": n.is_read} for n in notifs_rows.scalars().all()],
    }}


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(payload: dict = Depends(get_token_payload)):
    if payload["role"] != "ADMIN":
        raise forbidden("Admin access required")
    return payload


@admin_router.get("/users")
async def admin_list_users(page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
                            payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    skip = (page - 1) * limit
    rows = await db.execute(select(User).order_by(User.created_at.desc()).offset(skip).limit(limit))
    users = rows.scalars().all()
    total = await db.scalar(select(func.count()).select_from(User))
    return {"success": True, "data": {"users": [
        {"id": u.id, "email": u.email, "role": u.role.value, "isActive": u.is_active, "createdAt": u.created_at.isoformat()}
        for u in users
    ], "total": total, "page": page, "limit": limit}}


@admin_router.patch("/users/{user_id}/toggle")
async def toggle_user(user_id: str, payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    if user_id == payload["userId"]:
        raise bad_request("Cannot deactivate your own account")
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise not_found("User")
    user.is_active = not user.is_active
    await db.commit()
    return {"success": True, "data": {"user": {"id": user.id, "isActive": user.is_active}}}


@admin_router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, body: UserRoleUpdateBody, payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise not_found("User")
    user.role = body.role
    await db.commit()
    return {"success": True, "data": {"user": {"id": user.id, "role": user.role.value}}}


@admin_router.get("/stats")
async def get_stats(payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    from models.models import Community, CommunityStatus, EventStatus, ProjectStatus
    users = await db.scalar(select(func.count()).select_from(User))
    communities = await db.scalar(select(func.count()).select_from(Community).where(Community.status == CommunityStatus.ACTIVE))
    events = await db.scalar(select(func.count()).select_from(Event).where(Event.status == EventStatus.PUBLISHED))
    projects = await db.scalar(select(func.count()).select_from(Project).where(Project.status != ProjectStatus.CANCELLED))
    return {"success": True, "data": {"stats": {"users": users, "communities": communities, "events": events, "projects": projects}}}


@admin_router.get("/reports")
async def list_reports(payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(Report).order_by(Report.created_at.desc()))
    reports = rows.scalars().all()
    return {"success": True, "data": {"reports": [
        {"id": r.id, "contentType": r.content_type, "contentId": r.content_id,
         "reason": r.reason, "status": r.status.value, "createdAt": r.created_at.isoformat()}
        for r in reports
    ]}}


@admin_router.patch("/reports/{report_id}")
async def update_report(report_id: str, body: ReportStatusBody, payload: dict = Depends(_require_admin), db: AsyncSession = Depends(get_db)):
    report = await db.scalar(select(Report).where(Report.id == report_id))
    if not report:
        raise not_found("Report")
    report.status = body.status
    await db.commit()
    return {"success": True, "data": {"report": {"id": report.id, "status": report.status.value}}}
