"""
SQLAlchemy ORM models matching the Prisma schema.
All table names match the @@map() directives in schema.prisma.
"""
import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, DateTime, Integer, ForeignKey,
    Enum as SAEnum, Text, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .database import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    STUDENT = "STUDENT"
    ADMIN = "ADMIN"

class MembershipRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MODERATOR = "MODERATOR"
    MEMBER = "MEMBER"

class MembershipStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    BANNED = "BANNED"

class CommunityVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"

class CommunityStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"

class ProjectStatus(str, enum.Enum):
    IDEA = "IDEA"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    CANCELLED = "CANCELLED"

class CollaborationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"

class NotificationType(str, enum.Enum):
    MEMBERSHIP_APPROVED = "MEMBERSHIP_APPROVED"
    MEMBERSHIP_REJECTED = "MEMBERSHIP_REJECTED"
    MEMBERSHIP_REQUEST = "MEMBERSHIP_REQUEST"
    EVENT_REGISTERED = "EVENT_REGISTERED"
    EVENT_UPDATED = "EVENT_UPDATED"
    EVENT_CANCELLED = "EVENT_CANCELLED"
    PROJECT_INVITE = "PROJECT_INVITE"
    COLLABORATION_REQUEST = "COLLABORATION_REQUEST"
    COLLABORATION_ACCEPTED = "COLLABORATION_ACCEPTED"
    COLLABORATION_REJECTED = "COLLABORATION_REJECTED"
    COMMUNITY_ANNOUNCEMENT = "COMMUNITY_ANNOUNCEMENT"
    GENERAL = "GENERAL"

class ReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"

class ResourceType(str, enum.Enum):
    ROOM = "ROOM"
    EQUIPMENT = "EQUIPMENT"
    SOFTWARE = "SOFTWARE"
    OTHER = "OTHER"


# ── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column("passwordHash", String, nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="userrole"), default=UserRole.STUDENT)
    email_verified: Mapped[bool] = mapped_column("emailVerified", Boolean, default=False)
    is_active: Mapped[bool] = mapped_column("isActive", Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    profile: Mapped[Optional["UserProfile"]] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[List["Session"]] = relationship(back_populates="user")
    community_memberships: Mapped[List["CommunityMembership"]] = relationship(back_populates="user")
    owned_communities: Mapped[List["Community"]] = relationship(back_populates="owner", foreign_keys="Community.owner_id")
    event_registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="user")
    project_memberships: Mapped[List["ProjectMembership"]] = relationship(back_populates="user")
    owned_projects: Mapped[List["Project"]] = relationship(back_populates="owner", foreign_keys="Project.owner_id")
    collaboration_requests: Mapped[List["CollaborationRequest"]] = relationship(back_populates="sender", foreign_keys="CollaborationRequest.sender_id")
    discussions: Mapped[List["Discussion"]] = relationship(back_populates="author")
    comments: Mapped[List["Comment"]] = relationship(back_populates="author")
    notifications: Mapped[List["Notification"]] = relationship(back_populates="user")
    created_events: Mapped[List["Event"]] = relationship(back_populates="creator", foreign_keys="Event.creator_id")

    __table_args__ = (Index("ix_users_email", "email"),)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    display_name: Mapped[str] = mapped_column("displayName", String, nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column("avatarUrl", String)
    college: Mapped[Optional[str]] = mapped_column(String)
    course: Mapped[Optional[str]] = mapped_column(String)
    academic_year: Mapped[Optional[str]] = mapped_column("academicYear", String)
    skills: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    interests: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    github_url: Mapped[Optional[str]] = mapped_column("githubUrl", String)
    linkedin_url: Mapped[Optional[str]] = mapped_column("linkedinUrl", String)
    website_url: Mapped[Optional[str]] = mapped_column("websiteUrl", String)
    is_public: Mapped[bool] = mapped_column("isPublic", Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column("expiresAt", DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[Optional[str]] = mapped_column("ipAddress", String)
    user_agent: Mapped[Optional[str]] = mapped_column("userAgent", String)

    user: Mapped["User"] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_token", "token"),
        Index("ix_sessions_user_id", "userId"),
    )


class Community(Base):
    __tablename__ = "communities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column("logoUrl", String)
    cover_url: Mapped[Optional[str]] = mapped_column("coverUrl", String)
    objectives: Mapped[Optional[str]] = mapped_column(Text)
    rules: Mapped[Optional[str]] = mapped_column(Text)
    visibility: Mapped[CommunityVisibility] = mapped_column(SAEnum(CommunityVisibility, name="communityvisibility"), default=CommunityVisibility.PUBLIC)
    status: Mapped[CommunityStatus] = mapped_column(SAEnum(CommunityStatus, name="communitystatus"), default=CommunityStatus.ACTIVE)
    website_url: Mapped[Optional[str]] = mapped_column("websiteUrl", String)
    owner_id: Mapped[str] = mapped_column("ownerId", String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="owned_communities", foreign_keys=[owner_id])
    memberships: Mapped[List["CommunityMembership"]] = relationship(back_populates="community")
    events: Mapped[List["Event"]] = relationship(back_populates="community")
    projects: Mapped[List["Project"]] = relationship(back_populates="community")
    discussions: Mapped[List["Discussion"]] = relationship(back_populates="community")


class CommunityMembership(Base):
    __tablename__ = "community_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"))
    community_id: Mapped[str] = mapped_column("communityId", String, ForeignKey("communities.id", ondelete="CASCADE"))
    role: Mapped[MembershipRole] = mapped_column(SAEnum(MembershipRole, name="membershiprole"), default=MembershipRole.MEMBER)
    status: Mapped[MembershipStatus] = mapped_column(SAEnum(MembershipStatus, name="membershipstatus"), default=MembershipStatus.PENDING)
    joined_at: Mapped[Optional[datetime]] = mapped_column("joinedAt", DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="community_memberships")
    community: Mapped["Community"] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("userId", "communityId", name="uq_community_membership"),
        Index("ix_community_memberships_community_id", "communityId"),
        Index("ix_community_memberships_user_id", "userId"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    community_id: Mapped[Optional[str]] = mapped_column("communityId", String, ForeignKey("communities.id"))
    creator_id: Mapped[str] = mapped_column("creatorId", String, ForeignKey("users.id"))
    venue: Mapped[Optional[str]] = mapped_column(String)
    meeting_link: Mapped[Optional[str]] = mapped_column("meetingLink", String)
    start_at: Mapped[datetime] = mapped_column("startAt", DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column("endAt", DateTime(timezone=True))
    max_capacity: Mapped[Optional[int]] = mapped_column("maxCapacity", Integer)
    status: Mapped[EventStatus] = mapped_column(SAEnum(EventStatus, name="eventstatus"), default=EventStatus.DRAFT)
    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    community: Mapped[Optional["Community"]] = relationship(back_populates="events")
    creator: Mapped["User"] = relationship(back_populates="created_events", foreign_keys=[creator_id])
    registrations: Mapped[List["EventRegistration"]] = relationship(back_populates="event")


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_id: Mapped[str] = mapped_column("eventId", String, ForeignKey("events.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"))
    registered_at: Mapped[datetime] = mapped_column("registeredAt", DateTime(timezone=True), server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="registrations")
    user: Mapped["User"] = relationship(back_populates="event_registrations")

    __table_args__ = (
        UniqueConstraint("eventId", "userId", name="uq_event_registration"),
        Index("ix_event_registrations_event_id", "eventId"),
        Index("ix_event_registrations_user_id", "userId"),
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    objectives: Mapped[Optional[str]] = mapped_column(Text)
    tech_stack: Mapped[List[str]] = mapped_column("techStack", ARRAY(String), default=list)
    category: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(SAEnum(ProjectStatus, name="projectstatus"), default=ProjectStatus.IDEA)
    owner_id: Mapped[str] = mapped_column("ownerId", String, ForeignKey("users.id"))
    community_id: Mapped[Optional[str]] = mapped_column("communityId", String, ForeignKey("communities.id"))
    repo_url: Mapped[Optional[str]] = mapped_column("repoUrl", String)
    demo_url: Mapped[Optional[str]] = mapped_column("demoUrl", String)
    required_skills: Mapped[List[str]] = mapped_column("requiredSkills", ARRAY(String), default=list)
    max_team_size: Mapped[Optional[int]] = mapped_column("maxTeamSize", Integer)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="owned_projects", foreign_keys=[owner_id])
    community: Mapped[Optional["Community"]] = relationship(back_populates="projects")
    memberships: Mapped[List["ProjectMembership"]] = relationship(back_populates="project")
    collaborations: Mapped[List["CollaborationRequest"]] = relationship(back_populates="project")


class ProjectMembership(Base):
    __tablename__ = "project_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column("projectId", String, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[MembershipRole] = mapped_column(SAEnum(MembershipRole, name="membershiprole"), default=MembershipRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column("joinedAt", DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="project_memberships")

    __table_args__ = (
        UniqueConstraint("projectId", "userId", name="uq_project_membership"),
        Index("ix_project_memberships_project_id", "projectId"),
    )


class CollaborationRequest(Base):
    __tablename__ = "collaboration_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column("projectId", String, ForeignKey("projects.id", ondelete="CASCADE"))
    sender_id: Mapped[str] = mapped_column("senderId", String, ForeignKey("users.id"))
    message: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[CollaborationStatus] = mapped_column(SAEnum(CollaborationStatus, name="collaborationstatus"), default=CollaborationStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="collaborations")
    sender: Mapped["User"] = relationship(back_populates="collaboration_requests", foreign_keys=[sender_id])

    __table_args__ = (
        Index("ix_collab_requests_project_id", "projectId"),
        Index("ix_collab_requests_sender_id", "senderId"),
    )


class Discussion(Base):
    __tablename__ = "discussions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    community_id: Mapped[str] = mapped_column("communityId", String, ForeignKey("communities.id", ondelete="CASCADE"))
    author_id: Mapped[str] = mapped_column("authorId", String, ForeignKey("users.id"))
    is_pinned: Mapped[bool] = mapped_column("isPinned", Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    community: Mapped["Community"] = relationship(back_populates="discussions")
    author: Mapped["User"] = relationship(back_populates="discussions")
    comments: Mapped[List["Comment"]] = relationship(back_populates="discussion")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    discussion_id: Mapped[str] = mapped_column("discussionId", String, ForeignKey("discussions.id", ondelete="CASCADE"))
    author_id: Mapped[str] = mapped_column("authorId", String, ForeignKey("users.id"))
    parent_id: Mapped[Optional[str]] = mapped_column("parentId", String, ForeignKey("comments.id"))
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    discussion: Mapped["Discussion"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(back_populates="comments")
    parent: Mapped[Optional["Comment"]] = relationship(remote_side="Comment.id", foreign_keys=[parent_id])
    replies: Mapped[List["Comment"]] = relationship(foreign_keys=[parent_id])


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column("userId", String, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(SAEnum(NotificationType, name="notificationtype"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column("isRead", Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_id", "userId"),
        Index("ix_notifications_is_read", "isRead"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    reporter_id: Mapped[str] = mapped_column("reporterId", String, ForeignKey("users.id"))
    reported_user_id: Mapped[Optional[str]] = mapped_column("reportedUserId", String, ForeignKey("users.id"))
    content_type: Mapped[str] = mapped_column("contentType", String, nullable=False)
    content_id: Mapped[str] = mapped_column("contentId", String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(SAEnum(ReportStatus, name="reportstatus"), default=ReportStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("updatedAt", DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    reporter: Mapped["User"] = relationship(foreign_keys=[reporter_id])
    reported_user: Mapped[Optional["User"]] = relationship(foreign_keys=[reported_user_id])
