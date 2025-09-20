from __future__ import annotations
import spacy
from sentence_transformers import SentenceTransformer, util
from groq import Groq,RateLimitError
import json
import os
from typing import Optional, Dict, List, Tuple
import dateparser
from datetime import datetime, timedelta
import re
from app.services.ml_utils import _filter_stats_
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type,wait_fixed
from app.model.llm import LLMExtractionInput, LLMExtractionOutput, ProposedEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventAgent:
    def __init__(self):
        print("Loading local ML models into memory...")
        self.nlp = spacy.load("en_core_web_sm")
        self.st_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        self.datetime_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # MM/DD/YYYY or DD/MM/YYYY
            r'\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b',  # Time patterns
            r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',  # Days
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b',  # Month Day
            r'\btomorrow\b|\bnext\s+week\b|\bthis\s+(?:week|month)\b',  # Relative dates
        ]
        
        api_keys_str = os.environ.get("GROQ_API_KEYS")
        if not api_keys_str:
            raise ValueError("GROQ_API_KEYS environment variable not set or empty")
        api_keys = [key.strip() for key in api_keys_str.split(',')]
        
        self.llm_clients = [Groq(api_key=key) for key in api_keys]
        self.client_index = 0
        if not self.llm_clients:
            raise ValueError("No valid Groq API keys found.")

        print(f"ML Models loaded. Found {len(self.llm_clients)} Groq API clients.")

    def _filter_layer_1(self, email_title: str, email_body: str) -> Dict[str, any]:
        """
        Enhanced Layer 1 with detailed scoring and reasoning
        Returns dict with pass/fail, confidence, and reasoning
        """
        email_body_lower = email_body.lower()
        email_title_lower = email_title.lower()
        
        stats = _filter_stats_(email_body_lower, email_title_lower, self.nlp)
        print(stats)
        
        result = {
            'passed': stats['final_decision'],
            'confidence': stats['total_score'],
            'reasons': stats['reasons'],
            'datetime_info': stats['datetime_filter']
        }
        
        return result

    def _filter_layer_2(self, email_body: str, user_interests: List[str]) -> Dict[str, any]:
        """
        Enhanced semantic filtering with multiple strategies
        """
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
    @retry(
        wait=wait_fixed(30),                          
        stop=stop_after_attempt(5),                   
        retry=retry_if_exception_type(RateLimitError),
        reraise=True                                  
    )
    def _filter_layer_3(self, email_title: str, email_body: str, user_interests: List[str]) -> Optional[Dict]:
        """
        Enhanced LLM extraction with better prompting and validation
        """
        if not self.llm_clients:
            logger.warning("No LLM clients available, skipping API call.")
            return None

        for _ in range(len(self.llm_clients)):
            current_client = self.llm_clients[self.client_index]
            current_key_index = self.client_index
        
            self.client_index = (self.client_index + 1) % len(self.llm_clients)

            try:

                today_iso = datetime.now().isoformat()
                
                prompt = f"""You are an expert event parser. Extract event details from the email content below. If multiple events are present pick the most relevant one to the user's interests for extraction.

        VALIDATION RULES:
        - Must be a real, upcoming event that someone can attend
        - Must have a specific date/time (not vague like "soon")
        - Ignore: past events, event summaries, speaker call-outs, generic announcements
        - Events must be within the next 6 months from today ({today_iso})
        - end_datetime should not exceed start_datetime by more than 7 days
        - convert all time to 24-format first then convert date_time to ISO format:
            EXAMPLE:  2023-10-05, 01:00 PM ->  2023-10-05, 13:00 -> 2023-10-05T13:00:00

        OUTPUT FORMAT - Return ONLY valid JSON:
        - If NOT a valid event: {{"valid": false}}
        - If valid event: {{
            "valid": true,
            "title": "Official event title (max 100 chars)",
            "location": "Event location if offline else or 'Online'",
            "summary": "2-line description of the event",
            "link": "Most relevant URL (registration/meeting/info)",
            "start_datetime": "date and time of the event in ISO 8601 format: YYYY-MM-DDTHH:MM:SS",
            "end_datetime": "If applicable,date and time in ISO 8601 format: YYYY-MM-DDTHH:MM:SS, else same as start_datetime",
            "relevant_interests": [list of matched user interests from: {user_interests}],
            "confidence": 0.95
        }}

        Use today's date ({today_iso}) as a reference for relative terms.

        EMAIL CONTENT:
        TITLE: {email_title[:200]}
        BODY: {email_body[:2000]}"""


            
                chat_completion = current_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.1-8b-instant", 
                    temperature=0.1,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                )
                
                data = json.loads(chat_completion.choices[0].message.content)
                
                if not data.get('valid', False):
                    return None

                start_datetime = data.get('start_datetime')
                if not data.get('end_datetime'):
                    data['end_datetime'] = start_datetime
                if start_datetime:
                    try:
                        parsed_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                        if parsed_dt <= datetime.now():
                            logger.warning(f"LLM extracted past date: {start_datetime}")
                            print(data)
                            return None
                    except ValueError:
                        logger.warning(f"Invalid datetime format from LLM: {start_datetime}")
                        return None
                
                return data
                
            except RateLimitError as e:
                logger.warning(f"Rate limit reached. Tenacity will retry... Details: {e}")
                raise
            except Exception as e:
                logger.error(f"Groq API extraction failed with a non-retriable error: {e}")
                return None
        logger.warning("All API keys are currently rate-limited. Triggering Tenacity retry wait...")
        raise RateLimitError("All Groq API keys are rate-limited.", response=None, body=None)

    def process_email(self, email_title: str, email_body: str, user_interests: List[str],source_message_id: str = None) -> Optional[ProposedEvent]:
        """
        Enhanced pipeline with detailed logging and fallback strategies
        """
        processing_log = {
            'email_title': email_title[:100] + "..." if len(email_title) > 100 else email_title,
            'layers': {}
        }
        
        layer1_result = self._filter_layer_1(email_title, email_body)
        processing_log['layers']['layer1'] = layer1_result
        
        if not layer1_result['passed']:
            logger.info(f"Layer 1 filtered out: {layer1_result['reasons']}")
            return None
        
        layer2_result = self._filter_layer_2(email_body, user_interests)
        processing_log['layers']['layer2'] = layer2_result
        
        if not layer2_result['passed']:
            logger.info(f"Layer 2 filtered out: {layer2_result['reasons']}")
            return None
        extracted_data = None
        try:
            extracted_data = self._filter_layer_3(email_title, email_body, user_interests)
        except Exception as e:
            logger.error(f"LLM extraction for '{email_title[:50]}...' failed permanently after all retries: {e}")
        processing_log['layers']['layer3'] = {'success': extracted_data is not None}
        
        if extracted_data:

            if not extracted_data.get('start_datetime'):
                logger.warning(f"LLM extracted data but was missing 'start_datetime' for: {extracted_data.get('title')}")
                return None
            
            logger.info(f"Successfully processed event: {extracted_data.get('title', 'Unknown')}")
            print(extracted_data)
            if extracted_data.get('relevant_interests'):
                return ProposedEvent(
                    title=extracted_data.get('title', 'Untitled Event'),
                    description=extracted_data.get('summary', ''),
                    location=extracted_data.get('location', 'Online'),
                    start_time=extracted_data.get('start_datetime'),
                    end_time=extracted_data.get('end_datetime', extracted_data.get('start_datetime')),
                    relevant_interests=extracted_data.get('relevant_interests', []),
                    link=extracted_data.get('link'),
                    source_message_id=source_message_id)
            
        logger.info("No event extracted after all layers")
        return None

async def extract_events(payload: LLMExtractionInput) -> LLMExtractionOutput:
    
    """Extract relevant events from emails using an LLM.
    
    This function processes emails through a 3-layer filtering system:
    1. Layer 1: Rule-based filtering (keywords, dates, footers)
    2. Layer 2: Semantic similarity matching with user interests
    3. Layer 3: LLM extraction and validation
    """
    try:
        # Initialize the EventAgent
        agent = EventAgent()
        
        # Combine regular interests and custom interests
        all_interests = payload.interests + payload.custom_interests
        
        extracted_events = []
        
        # Process each email
        for email in payload.emails:
            try:
                # Get email content - use subject as title, snippet as body preview
                email_title = email.subject or "No Subject"
                email_body = email.snippet or ""
                
                # If snippet is too short, we might need to extract from headers
                # Look for any content in headers that might be the full body
                if len(email_body) < 50:  # Snippet too short
                    for header in email.headers:
                        if header.name.lower() in ['body', 'content', 'text']:
                            email_body = header.value
                            break
                
                # Process the email through the ML pipeline
                proposed_event = agent.process_email(
                    email_title=email_title,
                    email_body=email_body,
                    user_interests=all_interests,
                    source_message_id=email.id

                )
                
                if proposed_event:
                    extracted_events.append(proposed_event)
                    logger.info(f"Successfully extracted event from email {email.id}: {proposed_event.title}")
                
            except Exception as e:
                logger.error(f"Failed to process email {email.id}: {e}")
                continue
        
        logger.info(f"Extracted {len(extracted_events)} events from {len(payload.emails)} emails")
        
        return LLMExtractionOutput(events=extracted_events)
        
    except Exception as e:
        logger.error(f"Critical error in extract_events: {e}")
        return LLMExtractionOutput(events=[])