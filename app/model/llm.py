from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class EmailHeader(BaseModel):
    name: str
    value: str


class EmailMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    subject: Optional[str] = None
    sender: Optional[str] = Field(default=None)
    to: Optional[str] = None
    date: Optional[str] = None
    internal_date: Optional[datetime] = None
    snippet: Optional[str] = None
    headers: List[EmailHeader] = Field(default_factory=list)


class LLMExtractionInput(BaseModel):
    user_id: str
    interests: List[str] = Field(default_factory=list)
    custom_interests: List[str] = Field(default_factory=list)
    emails: List[EmailMessage]


class ProposedEvent(BaseModel):
    source_message_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    link: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None


class LLMExtractionOutput(BaseModel):
    events: List[ProposedEvent] = Field(default_factory=list)


class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    source_message_id: Optional[str] = None
