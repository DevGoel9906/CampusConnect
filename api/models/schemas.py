from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, List, Any
from datetime import datetime
from models.models import (
    UserRole, MembershipRole, MembershipStatus, CommunityVisibility,
    CommunityStatus, EventStatus, ProjectStatus, CollaborationStatus,
    NotificationType, ReportStatus
)


# ── Pagination ───────────────────────────────────────────────────────────────

class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 20

    @field_validator("page")
    @classmethod
    def page_min(cls, v):
        return max(1, v)

    @field_validator("limit")
    @classmethod
    def limit_clamp(cls, v):
        return min(100, max(1, v))

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.limit


# ── Auth ─────────────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    display_name: str

    @field_validator("password")
    @classmethod
    def password_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 72:
            raise ValueError("Password too long")
        return v

    @field_validator("display_name")
    @classmethod
    def display_name_length(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Display name must be at least 2 characters")
        if len(v) > 60:
            raise ValueError("Display name too long")
        return v

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v):
        return v.lower()


class LoginBody(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v):
        return v.lower()


# ── Profile ───────────────────────────────────────────────────────────────────

class UpdateProfileBody(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    college: Optional[str] = None
    course: Optional[str] = None
    academic_year: Optional[str] = None
    skills: Optional[List[str]] = None
    interests: Optional[List[str]] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    is_public: Optional[bool] = None


# ── Community ─────────────────────────────────────────────────────────────────

class CommunityBody(BaseModel):
    name: str
    description: str
    category: str
    objectives: Optional[str] = None
    rules: Optional[str] = None
    visibility: Optional[CommunityVisibility] = CommunityVisibility.PUBLIC
    website_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_length(cls, v):
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Name too short")
        if len(v) > 100:
            raise ValueError("Name too long")
        return v

    @field_validator("description")
    @classmethod
    def desc_length(cls, v):
        v = v.strip()
        if len(v) < 20:
            raise ValueError("Description too short")
        return v


class CommunityUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    objectives: Optional[str] = None
    rules: Optional[str] = None
    visibility: Optional[CommunityVisibility] = None
    website_url: Optional[str] = None


class MemberRoleUpdateBody(BaseModel):
    role: MembershipRole


class MembershipReviewBody(BaseModel):
    action: str  # APPROVE | REJECT


# ── Event ─────────────────────────────────────────────────────────────────────

class EventBody(BaseModel):
    title: str
    description: str
    community_id: Optional[str] = None
    venue: Optional[str] = None
    meeting_link: Optional[str] = None
    start_at: datetime
    end_at: datetime
    max_capacity: Optional[int] = None
    tags: Optional[List[str]] = None
    status: Optional[EventStatus] = EventStatus.DRAFT


class EventUpdateBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    community_id: Optional[str] = None
    venue: Optional[str] = None
    meeting_link: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    max_capacity: Optional[int] = None
    tags: Optional[List[str]] = None
    status: Optional[EventStatus] = None


# ── Project ───────────────────────────────────────────────────────────────────

class ProjectBody(BaseModel):
    title: str
    description: str
    objectives: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    category: str
    community_id: Optional[str] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    required_skills: Optional[List[str]] = None
    max_team_size: Optional[int] = None
    status: Optional[ProjectStatus] = ProjectStatus.IDEA


class ProjectUpdateBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    objectives: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    category: Optional[str] = None
    community_id: Optional[str] = None
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None
    required_skills: Optional[List[str]] = None
    max_team_size: Optional[int] = None
    status: Optional[ProjectStatus] = None


class CollaborationRequestBody(BaseModel):
    message: Optional[str] = None


class CollaborationReviewBody(BaseModel):
    action: str  # ACCEPT | REJECT


# ── Discussion ────────────────────────────────────────────────────────────────

class DiscussionBody(BaseModel):
    title: str
    body: str


class CommentBody(BaseModel):
    body: str
    parent_id: Optional[str] = None


# ── Admin ─────────────────────────────────────────────────────────────────────

class UserRoleUpdateBody(BaseModel):
    role: UserRole


class ReportStatusBody(BaseModel):
    status: ReportStatus
