from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class InterestOut(BaseModel):
    id: str
    category: str
    child: str


class SetUserInterestsRequest(BaseModel):
    interest_ids: List[str] = Field(default_factory=list)


class CustomInterestCreateRequest(BaseModel):
    name: str


class CustomInterestOut(BaseModel):
    id: str
    name: str


class EventOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    platform: Optional[str] = None
    link: Optional[str] = None
    startTime: datetime
    endTime: Optional[datetime] = None
    source: Optional[str] = None
    sourceId: Optional[str] = None


class UserProfileOut(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    interests: List[InterestOut] = Field(default_factory=list)
    custom_interests: List[CustomInterestOut] = Field(default_factory=list)


class StatusResponse(BaseModel):
    status: str = "ok"
