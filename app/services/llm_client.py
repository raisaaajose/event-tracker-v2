from __future__ import annotations
import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import google.api_core.exceptions

from app.model.llm import LLMExtractionInput, LLMExtractionOutput, ProposedEvent, EmailMessage
from app.constants.constants import NON_EVENT_KEYWORDS
from app.core.db import db 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AsyncEventAgent:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        
        api_keys_str = os.environ.get("GEMINI_API_KEYS", "")
        self.api_keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
        
        if not self.api_keys:
            raise ValueError("GEMINI_API_KEYS environment variable not set")

        self.models = []
        for key in self.api_keys:
            model = genai.GenerativeModel(
                model_name="gemini-3.5-flash",
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8000,
                    response_mime_type="application/json",
                ),
            )
            self.models.append(model)
        
        genai.configure(api_key=self.api_keys[0])

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): self.thread_pool.shutdown(wait=True)

    def _safe_parse_iso(self, dt_str: str) -> datetime:
        """Parses ISO strings and ensures they are timezone-aware (UTC)."""
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    def _execute_gemini_batch_call(self, emails: List[Dict], user_interests: List[str], model) -> List[Dict]:
        """Synchronous wrapper for the Gemini API call."""
        logger.info(f"DEBUG: Entering Gemini Call with {len(emails)} emails...")
        today_iso = datetime.now(timezone.utc).isoformat()
        
        emails_text = ""
        for e in emails:
            emails_text += f"--- EMAIL_START (ID: {e['id']}) ---\n"
            emails_text += f"Subject: {e['subject']}\nContent: {e['content']}\n"
            emails_text += f"--- EMAIL_END ---\n\n"

        prompt = f"""
        SYSTEM ROLE:
        You are a highly precise Event Extraction Agent. Parse the batch of emails below.
        USER INTERESTS: {user_interests}

        ID MAPPING:
        Each email has an ID in its header (e.g., ID: 123). 
        You MUST return that exact ID in the 'source_message_id' field for every event found in that email.

        RULES:
        1. Extract events between {today_iso} and 12 months out.
        2. DURATION: Max 7 days.
        3. Return ONLY a valid JSON array.

        JSON SCHEMA:
        [
        {{
            "source_message_id": "The exact ID from the EMAIL_START header",
            "title": "Official event name",
            "location": "Address or 'Online'",
            "summary": "2-line description",
            "link": "Registration URL",
            "start_datetime": "ISO 8601 format",
            "end_datetime": "ISO 8601 format",
            "relevant_interests": ["List of matched interests"],
            "valid": true
        }}
        ]

        EMAILS:
        {emails_text}
        """

        try:
            logger.info("DEBUG: Sending request to Google Generative AI...")
            response = model.generate_content(prompt)
            
            logger.info("DEBUG: Received response from Google!")
            logger.info(f"DEBUG: RAW RESPONSE TEXT: {response.text}")
            raw_text = response.text.strip()
            start_idx = raw_text.find('[')
            end_idx = raw_text.rfind(']')
            
            if start_idx == -1 or end_idx == -1:
                logger.info(f"DEBUG: ❌ No JSON array found in response: {raw_text}")
                return []
                
            clean_json = raw_text[start_idx:end_idx + 1]
            events = json.loads(clean_json)
            
            logger.info(f"DEBUG: Parsed {len(events) if isinstance(events, list) else 0} events from JSON.")
            
            valid_results = []
            now = datetime.now(timezone.utc)
            allowed_ids = {e['id'] for e in emails}

            for ev in (events if isinstance(events, list) else []):
                sid = ev.get("source_message_id")
                start_str = ev.get("start_datetime")
                
                logger.info(f"DEBUG: Evaluating event '{ev.get('title')}' for ID {sid}")

                if not start_str or sid not in allowed_ids:
                    logger.info(f"DEBUG: ❌ Event failed ID validation (sid: {sid})")
                    continue
                    
                try:
                    start = self._safe_parse_iso(start_str)
                    logger.info(f"DEBUG: Event date {start} vs Now {now}")
                    valid_results.append(ev)
                except Exception as parse_err:
                    logger.info(f"DEBUG: ❌ Date parsing failed: {parse_err}")
            
            return valid_results

        except Exception as e:
            logger.info(f"DEBUG: CRITICAL ERROR DURING GEMINI CALL: {e}")
            import traceback
            traceback.print_exc()
            return []

        


    async def _is_new_event(self, email: EmailMessage) -> Optional[Dict]:
        """Layer 1 & DB check: Filters keywords and excludes existing IDs from DB."""
        body = (email.snippet or "") + " ".join([h.value for h in (email.headers or []) if h.name.lower() in ["body", "content"]])
        body_lower = body.lower()
        
        logger.info(f"DEBUG: Checking Email ID: {email.id}")

        for kw in NON_EVENT_KEYWORDS:
            if kw.lower() in body_lower:
                logger.info(f"DEBUG: ❌ Email {email.id} skipped due to keyword: '{kw}'")
                return None

        exists = await db.event.find_unique(where={"sourceId": email.id})
        if exists:
            logger.info(f"DEBUG: ❌ Email {email.id} skipped because it already exists in DB.")
            return None

        logger.info(f"DEBUG: ✅ Email {email.id} passed filters. Sending to Gemini...")
        return {"id": email.id, "subject": email.subject or "No Subject", "content": body[:2000]}


    async def process_emails_batch_async(self, emails: List[EmailMessage], interests: List[str]) -> List[ProposedEvent]:
        pre_filtered = await asyncio.gather(*[self._is_new_event(e) for e in emails])
        valid_emails = [f for f in pre_filtered if f]
        if not valid_emails: return []

        # Chunking into groups of 5
        chunk_size = 5
        chunks = [valid_emails[i:i + chunk_size] for i in range(0, len(valid_emails), chunk_size)]
        
        # Process chunks in parallel using rotating models
        tasks = []
        loop = asyncio.get_event_loop()
        for i, chunk in enumerate(chunks):
            model = self.models[i % len(self.models)]
            tasks.append(loop.run_in_executor(self.thread_pool, self._execute_gemini_batch_call, chunk, interests, model))

        chunk_results = await asyncio.gather(*tasks)
        
        # Map back to ProposedEvent objects
        final_events = []
        for events_list in chunk_results:
            for data in events_list:
                try:
                    final_events.append(ProposedEvent(
                        source_message_id=data["source_message_id"],
                        title=data["title"],
                        description=data["summary"],
                        location=data["location"],
                        start_time=self._safe_parse_iso(data["start_datetime"]),
                        end_time=self._safe_parse_iso(data["end_datetime"]),
                        link=data.get("link")
                    ))
                except Exception as e:
                    logger.error(f"Mapping error: {e}")
        return final_events

async def extract_events(payload: LLMExtractionInput) -> LLMExtractionOutput:
    try:
        async with AsyncEventAgent() as agent:
            events = await agent.process_emails_batch_async(payload.emails, payload.interests + payload.custom_interests)
            return LLMExtractionOutput(events=events)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return LLMExtractionOutput(events=[])