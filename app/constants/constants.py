import re
from typing import List, Set, Tuple


NON_EVENT_KEYWORDS: Set[str] = {"congratulations", "bus fare", "birthday"}

STRONG_EVENT_KEYWORDS: Set[str] = {
    "register now",
    "registration open",
    "rsvp",
    "save the date",
    "join us for",
    "you're invited",
    "invitation to",
    "attend",
    "workshop",
    "seminar",
    "webinar",
    "conference",
    "symposium",
    "meeting scheduled",
    "call scheduled",
    "session",
    "training",
    "demo",
    "presentation",
    "talk",
    "lecture",
    "panel",
    "job opening",
    "career opportunity",
    "resume",
    "apply now",
    "hiring",
    "position available",
    "job alert",
    "internship",
}

WEAK_EVENT_KEYWORDS: Set[str] = {
    "event",
    "happening",
    "coming up",
    "scheduled",
    "calendar",
    "reminder",
    "meeting",
    "discussion",
    "session",
    "gathering",
}

TIME_KEYWORDS: Set[str] = {
    "today",
    "tomorrow",
    "this week",
    "next week",
    "this month",
    "next month",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "am",
    "pm",
    "morning",
    "afternoon",
    "evening",
    "noon",
    "midnight",
}

EVENT_URL_PATTERNS: List[Tuple[re.Pattern, float]] = [
    # High confidence patterns
    (re.compile(r"zoom\.us/j/\d+"), 0.9),
    (re.compile(r"meet\.google\.com/[a-z\-]+"), 0.9),
    (re.compile(r"teams\.microsoft\.com/l/meetup-join/"), 0.9),
    (re.compile(r"calendar\.google\.com/event"), 0.8),
    (re.compile(r"eventbrite\.com/e/"), 0.8),
    (re.compile(r"meetup\.com/.*events/"), 0.8),
    # Medium confidence patterns
    (re.compile(r"register\..*\.com"), 0.6),
    (re.compile(r"registration\..*\.edu"), 0.6),
    (re.compile(r"\.ics\b"), 0.7),
    (re.compile(r"calendly\.com/"), 0.7),
    # Lower confidence patterns
    (re.compile(r"forms\.gle/"), 0.4),
    (re.compile(r"bit\.ly/"), 0.3),
    (re.compile(r"tinyurl\.com/"), 0.3),
]

ACADEMIC_DOMAINS: Set[str] = {
    ".edu",
    ".ac.uk",
    ".ac.in",
    "university",
    "college",
    "institute",
}

EMAIL_FOOTER_KEYWORD: str = (
    "this message was sent from vellore institute of technology."
)
