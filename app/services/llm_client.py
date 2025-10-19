from __future__ import annotations
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import google.api_core.exceptions
import json
import os
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from app.model.llm import (
    LLMExtractionInput,
    LLMExtractionOutput,
    ProposedEvent,
    EmailMessage,
)

from app.constants.constants import (
    EMAIL_FOOTER_KEYWORD,
    NON_EVENT_KEYWORDS,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AsyncEventAgent:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        api_keys_str = os.environ.get("GEMINI_API_KEYS")
        if not api_keys_str:
            raise ValueError("GEMINI_API_KEYS environment variable not set or empty")

        self.api_keys = [key.strip() for key in api_keys_str.split(",")]
        self.client_index = 0

        if not self.api_keys:
            raise ValueError("No valid Gemini API keys found.")

        self.models = []
        for i, api_key in enumerate(self.api_keys):
            genai.configure(api_key=api_key)  # type: ignore[attr-defined]
            model = genai.GenerativeModel(  # type: ignore[attr-defined]
                model_name="gemini-2.0-flash-exp",
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8000,
                    response_mime_type="application/json",
                ),
            )
            self.models.append((api_key, model))

        logger.info(
            f"ML Models loaded. Found {len(self.api_keys)} Gemini API keys with {max_workers} workers."
        )

        if len(self.api_keys) == 1:
            logger.info(
                "Single API key detected - will process batches sequentially to avoid rate limits"
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.thread_pool.shutdown(wait=True)

    def _run_in_thread(self, func, *args, **kwargs):
        """Run CPU-bound operations in thread pool"""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.thread_pool, func, *args, **kwargs)

    def _execute_gemini_call(
        self,
        filtered_emails: List[Dict],
        user_interests: List[str],
        api_key: str,
        model,
    ) -> List[Dict]:
        """
        Synchronous method to execute a single, non-retrying API call to Gemini and designed to run in a thread.
        """
        genai.configure(api_key=api_key) 
        today_iso = datetime.now().isoformat()

        emails_text = ""
        for i, email in enumerate(filtered_emails):
            emails_text += f"\n--- EMAIL {i + 1} (ID: {email['id']}) ---\n"
            emails_text += f"Subject: {email['subject']}\n"
            emails_text += f"Content: {email['content']}\n"

        prompt = f"""You are an expert event parser.These events could also be deadlines .Extract event details from the emails below and return them as a JSON array.

VALIDATION RULES:
- Must be a real, upcoming event or deadline that is relevant to the user's interests: {user_interests}
- Events must be within the next 6 months from today
- For internships, use DEADLINE as start_datetime (the last date to apply)
- For events/workshops, use the EVENT START DATE as start_datetime
- comprehend the meaning of the email fully and create the json accordingly

OUTPUT FORMAT - Return ONLY a JSON array of valid events:
[
  {{
    "source_message_id": "{email["id"]}",
    "title": "Official event title (max 100 chars)",
    "location": "Event location if offline else 'Online'",
    "summary": "2-line description of the event",
    "link": "Most relevant URL (registration/meeting/info)",
    "start_datetime": "YYYY-MM-DDTHH:MM:SS - Must be explicitly mentioned in email,
    "date_source": "REQUIRED: Quote the EXACT text from email containing the date (e.g., 'Deadline: 20/10/2025')",
    "end_datetime": "Same as start_datetime for deadlines, or event end date",
    "relevant_interests": ["list of matched interests from: {user_interests}"],
    "valid": true
  }}
]

If no valid events found, return: [summary of event in one line and why it was invalid]




EMAILS:{emails_text}"""

        response_text = ""
        try:
            response = model.generate_content(prompt)
            response_text = response.text
            if not response_text:
                logger.warning(
                    f"Empty response from Gemini on API key ending in ...{api_key[-4:]}"
                )
                return []

            events = json.loads(response_text)
            logger.info(
                f"Gemini returned {len(events)} events for batch of {len(filtered_emails)} emails"
            )

            if not isinstance(events, list):
                logger.warning(f"Expected list of events, got: {type(events)}")
                return []

            valid_events = []
            for event in events:
                if not isinstance(event, dict) or not event.get("valid", False):
                    continue
                start_datetime = event.get("start_datetime")
                if not start_datetime:
                    continue
                try:
                    parsed_dt = datetime.fromisoformat(
                        start_datetime.replace("Z", "+00:00")
                    )
                    if parsed_dt <= datetime.now():
                        continue
                except ValueError:
                    continue
                if not event.get("end_datetime"):
                    event["end_datetime"] = start_datetime
                valid_events.append(event)

            logger.info(
                f"{len(valid_events)} valid events after post-processing filters."
            )
            return valid_events

        except (json.JSONDecodeError, google.api_core.exceptions.GoogleAPIError) as e:
            logger.warning(
                f"API call failed for key ...{api_key[-4:]}: {e}. This may trigger a retry."
            )
            if isinstance(e, json.JSONDecodeError):
                logger.error(
                    f"--- RAW GEMINI RESPONSE ---:\n{response_text}\n--- END RAW RESPONSE ---"
                )
            raise e
        except Exception as e:
            logger.error(f"An unexpected error occurred during Gemini call: {e}")
            raise e

    async def _process_gemini_batch(
        self,
        emails: List[Dict],
        user_interests: List[str],
    ) -> List[Dict]:
        """Process a single batch through Gemini API with rotational retry logic"""
        max_retry_cycles = 5
        total_cycles = 1 + max_retry_cycles
        wait_between_cycles_seconds = 60

        last_exception = None

        for cycle in range(total_cycles):
            if cycle > 0:
                logger.warning(
                    f"Starting retry cycle {cycle}/{max_retry_cycles} for batch after waiting "
                    f"{wait_between_cycles_seconds} seconds."
                )
            else:
                logger.info("Starting initial attempt cycle for batch.")

            max_attempts_per_key = 3
            num_keys = len(self.models)
            total_rotational_attempts = num_keys * max_attempts_per_key

            for attempt in range(total_rotational_attempts):
                key_index = attempt % num_keys
                api_key, model = self.models[key_index]
                key_display = f"...{api_key[-4:]}"

                logger.info(
                    f"Cycle {cycle + 1}, Rotational Attempt {attempt + 1}/{total_rotational_attempts}, "
                    f"using API key index {key_index} ({key_display})."
                )

                try:
                    result = await self._run_in_thread(
                        self._execute_gemini_call,
                        emails,
                        user_interests,
                        api_key,
                        model,
                    )
                    logger.info(f"Successfully processed batch in cycle {cycle + 1}.")
                    return result

                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"Rotational attempt {attempt + 1} failed. Retrying with next key..."
                    )
                    await asyncio.sleep(2)
                    
            if cycle < total_cycles - 1:
                logger.warning(
                    f"Full attempt cycle {cycle + 1} failed. Waiting {wait_between_cycles_seconds} "
                    "seconds before the next retry cycle."
                )
                await asyncio.sleep(wait_between_cycles_seconds)

        logger.error(
            f"All {total_cycles} attempt cycles failed for the batch. Last known error: {last_exception}"
        )
        if last_exception:
            raise last_exception
        raise Exception("All Gemini API attempts and retries failed for the batch.")

    async def _process_all_batches(
        self, email_batches: List[List[Dict]], user_interests: List[str]
    ) -> List[Dict]:
        """Process multiple batches of emails through Gemini in parallel"""
        if not email_batches:
            return []

        tasks = [
            self._process_gemini_batch(batch, user_interests)
            for batch in email_batches
        ]

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_events = []
        for idx, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(f"Batch {idx} processing failed: {result}")
                continue
            if isinstance(result, list):
                all_events.extend(result)
                
        logger.info(
            f"Successfully gathered {len(all_events)} events from {len(email_batches)} batches."
        )
        return all_events
    
    def _chunk_emails(
        self, emails: List[Dict], chunk_size: int = 10
    ) -> List[List[Dict]]:
        """Split emails into chunks for parallel processing"""
        chunks = []
        for i in range(0, len(emails), chunk_size):
            chunks.append(emails[i : i + chunk_size])
        return chunks

    async def process_emails_batch_async(
        self, emails: List[EmailMessage], user_interests: List[str]
    ) -> List[ProposedEvent]:
        """Async batch email processing with parallel execution"""
        logger.info(f"Starting batch processing of {len(emails)} emails")

        # Convert emails to dict format
        email_dicts = []
        for email in emails:
            email_title = email.subject or ""
            email_body = email.body or ""

            if not email_body and email.headers:
                email_body = " ".join(
                    [h.value for h in email.headers if h.name.lower() in ["body", "content"]]
                )

            email_dicts.append({
                "id": email.id,
                "subject": email_title,
                "content": email_body,
            })

        logger.info(f"Prepared {len(email_dicts)} emails for processing")

        # Split into batches of 10
        email_chunks = self._chunk_emails(email_dicts, chunk_size=10)
        logger.info(f"Created {len(email_chunks)} chunks of emails")

        # Process all batches through Gemini
        extracted_events_data = await self._process_all_batches(
            email_chunks, user_interests
        )

        # Convert to ProposedEvent objects
        proposed_events = []
        logger.info(f"Converting {len(extracted_events_data)} events to ProposedEvent objects")

        default_tz_name = os.getenv("DEFAULT_EVENT_TIMEZONE", "Asia/Kolkata")
        try:
            default_tz = ZoneInfo(default_tz_name)
        except Exception:
            logger.warning(
                f"Invalid DEFAULT_EVENT_TIMEZONE='{default_tz_name}', falling back to UTC"
            )
            default_tz = timezone.utc

        for event_data in extracted_events_data:
            try:
                start_dt_str = event_data.get("start_datetime")
                end_dt_str = event_data.get("end_datetime", start_dt_str)

                if not start_dt_str:
                    logger.error(f"Gemini event missing 'start_datetime': {event_data}")
                    continue
                if not end_dt_str:
                    end_dt_str = start_dt_str

                start_time = datetime.fromisoformat(start_dt_str.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end_dt_str.replace("Z", "+00:00"))

                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=default_tz)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=default_tz)

                proposed_event = ProposedEvent(
                    source_message_id=event_data.get("source_message_id"),
                    title=event_data.get("title", "Untitled Event"),
                    description=event_data.get("summary", ""),
                    location=event_data.get("location", "Online"),
                    start_time=start_time,
                    end_time=end_time,
                    link=event_data.get("link"),
                )
                proposed_events.append(proposed_event)
                logger.info(
                    f"Successfully created ProposedEvent: '{proposed_event.title}'"
                )
            except Exception as e:
                logger.error(
                    f"Failed to create ProposedEvent from Gemini data {event_data}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"Final result: {len(proposed_events)} events extracted from {len(emails)} emails (tz={default_tz_name})."
        )
        return proposed_events


async def extract_events_async(payload: LLMExtractionInput) -> LLMExtractionOutput:
    """Async extraction with parallel processing"""
    try:
        async with AsyncEventAgent(max_workers=4) as agent:
            all_interests = payload.interests + payload.custom_interests
            extracted_events = await agent.process_emails_batch_async(
                payload.emails, all_interests
            )
            logger.info(
                f"Extracted {len(extracted_events)} events from {len(payload.emails)} emails"
            )
            logger.info(f"Number of events extracted: {len(extracted_events)}")
            return LLMExtractionOutput(events=extracted_events)

    except Exception as e:
        logger.error(f"Critical error in extract_events_async: {e}")
        return LLMExtractionOutput(events=[])


async def extract_events(payload: LLMExtractionInput) -> LLMExtractionOutput:
    """Main entry point"""
    return await extract_events_async(payload)
