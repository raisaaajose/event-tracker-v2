from __future__ import annotations
import spacy
from sentence_transformers import SentenceTransformer, util
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import json
import os
from typing import Optional, Dict, List, Tuple
import dateparser
from datetime import datetime, timedelta
import re
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import functools
from app.services.ml_utils import _filter_stats_
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, wait_fixed
from app.model.llm import LLMExtractionInput, LLMExtractionOutput, ProposedEvent, EmailMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AsyncEventAgent:
    def __init__(self, max_workers: int = 4):
        self.nlp = spacy.load("en_core_web_sm")
        self.st_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        
        self.datetime_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
            r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b',
            r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b',
            r'\btomorrow\b|\bnext\s+week\b|\bthis\s+(?:week|month)\b',
        ]
        
        # Configure Gemini
        api_keys_str = os.environ.get("GEMINI_API_KEYS")
        if not api_keys_str:
            raise ValueError("GEMINI_API_KEYS environment variable not set or empty")
        
        self.api_keys = [key.strip() for key in api_keys_str.split(',')]
        self.client_index = 0
        
        if not self.api_keys:
            raise ValueError("No valid Gemini API keys found.")

        # Initialize multiple models for parallel requests
        self.models = []
        for i, api_key in enumerate(self.api_keys):
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(
                model_name='gemini-2.0-flash-exp',
                generation_config=GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8000,
                    response_mime_type="application/json"
                )
            )
            self.models.append((api_key, model))

        logger.info(f"ML Models loaded. Found {len(self.api_keys)} Gemini API keys with {max_workers} workers.")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.thread_pool.shutdown(wait=True)

    def _run_in_thread(self, func, *args, **kwargs):
        """Run CPU-bound operations in thread pool"""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.thread_pool, func, *args, **kwargs)

    async def _filter_layer_1_async(self, email_title: str, email_body: str) -> Dict[str, any]:
        """Async version of Layer 1 filtering"""
        # Run the CPU-intensive NLP processing in a thread
        def _filter_sync():
            email_body_lower = email_body.lower()
            email_title_lower = email_title.lower()
            stats = _filter_stats_(email_body_lower, email_title_lower, self.nlp)
            return {
                'passed': stats['final_decision'],
                'confidence': stats['total_score'],
                'reasons': stats['reasons'],
                'datetime_info': stats['datetime_filter']
            }
        
        return await self._run_in_thread(_filter_sync)

    async def _filter_layer_2_async(self, email_body: str, user_interests: List[str]) -> Dict[str, any]:
        """Async version of Layer 2 filtering"""
        def _semantic_filter_sync():
            result = {
                'passed': False,
                'confidence': 0.0,
                'reasons': [],
                'scores': {}
            }
            
            if not user_interests:
                result.update({
                    'passed': True, 
                    'confidence': 0.5, 
                    'reasons': ["No user interests specified - allowing through"]
                })
                return result
            
            try:
                email_embedding = self.st_model.encode(email_body)
                interests_embeddings = self.st_model.encode(user_interests)
                
                direct_scores = util.cos_sim(email_embedding, interests_embeddings)
                max_direct_score = float(direct_scores.max())
                
                doc = self.nlp(email_body)
                key_phrases = [chunk.text.lower() for chunk in doc.noun_chunks 
                              if len(chunk.text.split()) <= 3 and len(chunk.text) > 3]
                
                topic_scores = []
                if key_phrases:
                    phrases_embedding = self.st_model.encode(key_phrases)
                    phrase_similarity = util.cos_sim(phrases_embedding, interests_embeddings)
                    topic_scores = phrase_similarity.max(dim=1).values.tolist()
                
                max_topic_score = max(topic_scores) if topic_scores else 0.0
                combined_score = max(max_direct_score, max_topic_score * 0.8)
                
                base_threshold = 0.3
                content_length_factor = min(0.2, len(email_body) / 5000)
                interests_factor = min(0.2, len(user_interests) / 10)
                adaptive_threshold = base_threshold - content_length_factor - interests_factor
                
                result.update({
                    'passed': combined_score > adaptive_threshold,
                    'confidence': combined_score,
                    'scores': {
                        'direct_similarity': max_direct_score,
                        'topic_similarity': max_topic_score,
                        'combined_score': combined_score,
                        'threshold_used': adaptive_threshold
                    },
                    'reasons': [f"Semantic similarity: {combined_score:.3f} vs threshold {adaptive_threshold:.3f}"]
                })
                
            except Exception as e:
                logger.error(f"Layer 2 filtering failed: {e}")
                result.update({
                    'passed': True, 
                    'confidence': 0.5,
                    'reasons': [f"Error in semantic analysis, allowing through: {str(e)}"]
                })
            
            return result

        return await self._run_in_thread(_semantic_filter_sync)

    async def _process_single_email_layers_1_2(self, email: EmailMessage, user_interests: List[str]) -> Optional[Dict]:
        """Process a single email through layers 1 and 2 concurrently"""
        email_title = email.subject or ""
        email_body = email.snippet or ""
        
        if not email_body and email.headers:
            email_body = " ".join([h.value for h in email.headers if h.name.lower() in ['body', 'content']])
        
        processing_log = {
            'email_id': email.id,
            'email_title': email_title[:100] + "..." if len(email_title) > 100 else email_title,
            'layers': {}
        }
        
        # Run Layer 1 and 2 concurrently
        layer1_task = self._filter_layer_1_async(email_title, email_body)
        layer2_task = self._filter_layer_2_async(email_body, user_interests)
        
        layer1_result, layer2_result = await asyncio.gather(layer1_task, layer2_task)
        
        processing_log['layers']['layer1'] = layer1_result
        processing_log['layers']['layer2'] = layer2_result
        
        if not layer1_result['passed']:
            logger.info(f"Layer 1 filtered out email {email.id}: {layer1_result['reasons']}")
            return None
        
        if not layer2_result['passed']:
            logger.info(f"Layer 2 filtered out email {email.id}: {layer2_result['reasons']}")
            return None
        
        return {
            'id': email.id,
            'subject': email_title,
            'content': email_body,
            'processing_log': processing_log
        }

    async def _filter_layer_3_batch_async(self, filtered_emails_batches: List[List[Dict]], user_interests: List[str]) -> List[Dict]:
        """Process multiple batches of emails through Gemini in parallel"""
        if not filtered_emails_batches:
            return []

        # Create tasks for each batch with different API keys
        tasks = []
        for i, batch in enumerate(filtered_emails_batches):
            api_key, model = self.models[i % len(self.models)]
            task = self._process_gemini_batch(batch, user_interests, api_key, model)
            tasks.append(task)
        
        # Process all batches concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results from all batches
        all_events = []
        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Batch processing failed: {result}")
                continue
            if isinstance(result, list):
                all_events.extend(result)
        
        return all_events

    async def _process_gemini_batch(self, filtered_emails: List[Dict], user_interests: List[str], 
                                   api_key: str, model) -> List[Dict]:
        """Process a single batch through Gemini API"""
        def _call_gemini_sync():
            genai.configure(api_key=api_key)
            
            today_iso = datetime.now().isoformat()
            
            emails_text = ""
            for i, email in enumerate(filtered_emails):
                emails_text += f"\n--- EMAIL {i+1} (ID: {email['id']}) ---\n"
                emails_text += f"Subject: {email['subject']}\n"
                emails_text += f"Content: {email['content']}\n"
            
            prompt = f"""You are an expert event parser. Extract event details from the emails below and return them as a JSON array.

VALIDATION RULES:
- Must be a real, upcoming event that someone can attend
- Must have a specific date/time (not vague like "soon")
- Ignore: past events, event summaries, speaker call-outs, generic announcements
- Events must be within the next 6 months from today ({today_iso})
- end_datetime should not exceed start_datetime by more than 7 days
- Convert all times to 24-hour format first, then to ISO format

OUTPUT FORMAT - Return ONLY a JSON array of valid events:
[
  {{
    "source_message_id": "EMAIL_ID_FROM_ABOVE",
    "title": "Official event title (max 100 chars)",
    "location": "Event location if offline else 'Online'",
    "summary": "2-line description of the event",
    "link": "Most relevant URL (registration/meeting/info)",
    "start_datetime": "ISO 8601 format: YYYY-MM-DDTHH:MM:SS",
    "end_datetime": "ISO 8601 format: YYYY-MM-DDTHH:MM:SS, else same as start_datetime",
    "relevant_interests": ["list of matched interests from: {user_interests}"],
    "confidence": 0.95,
    "valid": true
  }}
]]

If no valid events found, return: []

EMAILS:{emails_text}"""

            try:
                response = model.generate_content(prompt)
                
                if not response.text:
                    logger.warning("Empty response from Gemini")
                    return []
                
                events = json.loads(response.text)
                
                if not isinstance(events, list):
                    logger.warning(f"Expected list of events, got: {type(events)}")
                    return []
                
                # Validate and filter events
                valid_events = []
                for event in events:
                    if not isinstance(event, dict) or not event.get('valid', False):
                        continue
                        
                    start_datetime = event.get('start_datetime')
                    if not start_datetime:
                        continue
                        
                    try:
                        parsed_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                        if parsed_dt <= datetime.now():
                            continue
                    except ValueError:
                        continue
                    
                    if not event.get('end_datetime'):
                        event['end_datetime'] = start_datetime
                    
                    valid_events.append(event)
                
                return valid_events
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}")
                return []
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                return []

        return await self._run_in_thread(_call_gemini_sync)

    def _chunk_emails(self, emails: List[Dict], chunk_size: int = 10) -> List[List[Dict]]:
        """Split emails into chunks for parallel processing"""
        chunks = []
        for i in range(0, len(emails), chunk_size):
            chunks.append(emails[i:i + chunk_size])
        return chunks

    async def process_emails_batch_async(self, emails: List[EmailMessage], user_interests: List[str]) -> List[ProposedEvent]:
        """Async version of batch email processing with parallel execution"""
        logger.info(f"Starting async batch processing of {len(emails)} emails")
        
        # Process Layer 1 & 2 for all emails concurrently
        email_tasks = [
            self._process_single_email_layers_1_2(email, user_interests) 
            for email in emails
        ]
        
        # Use asyncio.gather with batching to avoid overwhelming the system
        batch_size = min(20, len(email_tasks))  # Process in batches of 20
        filtered_emails = []
        
        for i in range(0, len(email_tasks), batch_size):
            batch_tasks = email_tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Email processing failed: {result}")
                elif result is not None:
                    filtered_emails.append(result)
        
        logger.info(f"After Layer 1&2 filtering: {len(filtered_emails)} emails remaining")
        
        if not filtered_emails:
            return []
        
        # Chunk emails for parallel LLM processing
        email_chunks = self._chunk_emails(filtered_emails, chunk_size=min(10, len(filtered_emails) // len(self.models) + 1))
        
        # Process chunks through Layer 3 in parallel
        extracted_events_data = await self._filter_layer_3_batch_async(email_chunks, user_interests)
        
        # Convert to ProposedEvent objects
        proposed_events = []
        for event_data in extracted_events_data:
            if event_data.get('relevant_interests'):
                try:
                    start_dt_str = event_data.get('start_datetime')
                    end_dt_str = event_data.get('end_datetime', start_dt_str)
                    if not start_dt_str:
                        logger.error(f"Missing start_datetime in event_data: {event_data}")
                        continue
                    # Defensive: if end_dt_str is None, use start_dt_str
                    if not end_dt_str:
                        end_dt_str = start_dt_str
                    start_time = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00')) if start_dt_str else None
                    end_time = datetime.fromisoformat(end_dt_str.replace('Z', '+00:00')) if end_dt_str else None
                    proposed_event = ProposedEvent(
                        source_message_id=event_data.get('source_message_id'),
                        title=event_data.get('title', 'Untitled Event'),
                        description=event_data.get('summary', ''),
                        location=event_data.get('location', 'Online'),
                        start_time=start_time,
                        end_time=end_time,
                        link=event_data.get('link'),
                    )
                    proposed_events.append(proposed_event)
                    logger.info(f"Successfully processed event: {proposed_event.title}")
                except Exception as e:
                    logger.error(f"Failed to create ProposedEvent from data {event_data}: {e}")
        
        logger.info(f"Final result: {len(proposed_events)} events extracted from batch")
        return proposed_events


# Updated main extraction function
async def extract_events_async(payload: LLMExtractionInput) -> LLMExtractionOutput:
    """Async version of event extraction with parallel processing"""
    try:
        async with AsyncEventAgent(max_workers=4) as agent:
            all_interests = payload.interests + payload.custom_interests
            extracted_events = await agent.process_emails_batch_async(payload.emails, all_interests)
            logger.info(f"Extracted {len(extracted_events)} events from {len(payload.emails)} emails")
            return LLMExtractionOutput(events=extracted_events)
        
    except Exception as e:
        logger.error(f"Critical error in extract_events_async: {e}")
        return LLMExtractionOutput(events=[])


# Wrapper to maintain compatibility with existing sync code
async def extract_events(payload: LLMExtractionInput) -> LLMExtractionOutput:
    """Main entry point - now async optimized"""
    return await extract_events_async(payload)
