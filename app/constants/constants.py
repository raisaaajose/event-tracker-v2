import re
from typing import List, Set, Tuple


NON_EVENT_KEYWORDS: Set[str] = {"congratulations", "bus fare", "birthday"}

# TIME_KEYWORDS: Set[str] = {
#     "today",
#     "tomorrow",
#     "this week",
#     "next week",
#     "this month",
#     "next month",
#     "monday",
#     "tuesday",
#     "wednesday",
#     "thursday",
#     "friday",
#     "saturday",
#     "sunday",
#     "am",
#     "pm",
#     "morning",
#     "afternoon",
#     "evening",
#     "noon",
#     "midnight",
# }


EMAIL_FOOTER_KEYWORD: str = (
    "this message was sent from vellore institute of technology."
)
