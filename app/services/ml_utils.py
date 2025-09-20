from typing import Set, List, Dict, Tuple
import re
import dateparser
from datetime import datetime

NON_EVENT_KEYWORDS: Set[str] = {
    "congratulations", "bus fare", "birthday"
}

STRONG_EVENT_KEYWORDS: Set[str] = {
    "register now", "registration open", "rsvp", "save the date",
    "join us for", "you're invited", "invitation to", "attend",
    "workshop", "seminar", "webinar", "conference", "symposium",
    "meeting scheduled", "call scheduled", "session", "training",
    "demo", "presentation", "talk", "lecture", "panel",
    "job opening", "career opportunity", "resume", "apply now", "hiring",
    "position available", "job alert", "internship", 
}

WEAK_EVENT_KEYWORDS: Set[str] = {
    "event", "happening", "coming up", "scheduled", "calendar",
    "reminder", "meeting", "discussion", "session", "gathering"
}

TIME_KEYWORDS: Set[str] = {
    "today", "tomorrow", "this week", "next week", "this month", "next month",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "am", "pm", "morning", "afternoon", "evening", "noon", "midnight"
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
    ".edu", ".ac.uk", ".ac.in", "university", "college", "institute"
}


def _calculate_keyword_score(email_body_lower: str, email_title_lower: str) -> Tuple[bool, float, List[str]]:
    """
    Calculate keyword-based scoring for event detection
    Returns: (should_continue, confidence_score, matched_keywords)
    """
    reasons = []
    content = email_title_lower + " " + email_body_lower
    
    for keyword in NON_EVENT_KEYWORDS:
        if keyword in content:
            return False, 0.0, [f"Non-event keyword found: {keyword}"]
    
    strong_matches = [kw for kw in STRONG_EVENT_KEYWORDS if kw in content]
    weak_matches = [kw for kw in WEAK_EVENT_KEYWORDS if kw in content]
    time_matches = [kw for kw in TIME_KEYWORDS if kw in content]
    
    score = 0.0
    score += len(strong_matches) * 0.4  
    score += len(weak_matches) * 0.2    
    score += min(len(time_matches) * 0.1, 0.3)  
    
    if strong_matches and time_matches:
        score += 0.2
    if len(strong_matches) >= 2:
        score += 0.1
        
    score = min(score, 1.0)
    
    reasons.extend([f"Strong: {strong_matches}", f"Weak: {weak_matches}", f"Time: {time_matches}"])
    
    return score > 0.1, score, reasons


def _calculate_url_score(email_content: str) -> Tuple[float, List[str]]:
    """
    Calculate URL-based confidence scoring
    """
    content_lower = email_content.lower()
    max_score = 0.0
    matched_patterns = []
    
    for pattern, confidence in EVENT_URL_PATTERNS:
        if pattern.search(content_lower):
            max_score = max(max_score, confidence)
            matched_patterns.append(f"{pattern.pattern}: {confidence}")
    
    return max_score, matched_patterns


def _check_academic_context(email_content: str) -> float:
    """
    Check if email comes from academic context (higher trust)
    """
    content_lower = email_content.lower()
    
    for domain in ACADEMIC_DOMAINS:
        if domain in content_lower:
            return 0.2  
            
    return 0.0

def _filter_by_footer(email_body_lower: str) -> bool:
    """
    Footer analysis for filtering out system emails
    """
    footer="this message was sent from vellore institute of technology."
    
    return footer in email_body_lower  

def contains_date_or_time(text: str, nlp_model) -> Tuple[bool, Tuple[List[str], List[str]]]:
    """
    Extracts all DATE and TIME entities from the text.

    It returns (False, None) if:
    1. No DATE or TIME entities are found at all.
    2. DATE entities are found, but ALL of them refer to dates in the past.

    On success, it returns (True, (date_strings, time_strings)).
    """
    doc = nlp_model(text)
    
    date_ents = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
    time_ents = [ent.text for ent in doc.ents if ent.label_ == "TIME"]
    
    import re
    text_lower = text.lower()
    
    time_patterns = [
    r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b',
    r'\b\d{1,2}\s*(?:am|pm)\b',
    r'\b\d{1,2}(?::\d{2})?\s*(?:-|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',
    r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:[A-Z]{2,5})\b',
    r'\b(?:noon|midnight|mid-day|EOD)\b',
]
    
    date_patterns = [
    r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
    r'\b\d{4}-\d{2}-\d{2}\b',
    r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s+\d{4})?\b',
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
    r'\b(?:on\s+)?(?:this|next|coming\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\b(?:today|tonight|tomorrow|end\s+of\s+(?:the\s+)?(?:day|week|month))\b',
]
    
    for pattern in time_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        time_ents.extend(matches)
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        date_ents.extend(matches)
    
    date_ents = list(set(date_ents))
    time_ents = list(set(time_ents))

    if not date_ents and not time_ents:
        return (False, None)
    if date_ents:
        has_future_or_present_date = False
        for date_str in date_ents:
            try:
                parsed_dt = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
                
                if parsed_dt and parsed_dt.date() >= datetime.now().date():
                    has_future_or_present_date = True
                    break 
                    
                
                weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                if any(day in date_str.lower() for day in weekdays):
                    has_future_or_present_date = True
                    break
                    
            except Exception:
                
                continue
        
        
        if not has_future_or_present_date:
            return (False, None)
    
    
    return (True, (date_ents, time_ents))

def _filter_stats_(email_body_lower: str, email_title_lower: str, nlp_model) -> Dict:
    """
    Keyword filtering with detailed scoring
    Returns: Dictionary with analysis results
    """
    reasons = []
    datetime_filter = False
    date_time = None
    
    should_continue, keyword_score, keyword_reasons = _calculate_keyword_score(
        email_body_lower, email_title_lower
    )
    reasons.extend(keyword_reasons)
    url_score, url_matches= 0.0, []
    academic_boost = 0.0
    footer_filtered = False
    total_score = 0.0
    final_decision = False
    if should_continue:
        
        url_score, url_matches = _calculate_url_score(email_title_lower + " " + email_body_lower)
        
        
        academic_boost = _check_academic_context(email_title_lower + " " + email_body_lower)
        
        
        total_score = keyword_score + url_score + academic_boost
        footer_filtered = _filter_by_footer(email_body_lower)
        if not footer_filtered:
            reasons.append("Filtered out by footer analysis")

        
        datetime_filter, date_time = contains_date_or_time(email_body_lower + " " + email_title_lower, nlp_model)
        if not datetime_filter:
            reasons.append("No valid future date/time found")

        
        threshold = 0.3
        if total_score < threshold:
            reasons.append(f"Total score {total_score:.2f} below threshold {threshold}")
        
        final_decision = total_score >= threshold and footer_filtered and datetime_filter

    return {
        'keyword_analysis': {
            'should_continue': should_continue,
            'score': keyword_score,
        },
        'url_analysis': {
            'score': url_score,
            'matches': url_matches
        },
        'academic_boost': academic_boost,
        'footer_filtered': footer_filtered,
        'total_score': total_score,
        'final_decision': final_decision,
        'datetime_filter': (datetime_filter, date_time),
        'reasons': reasons
    }