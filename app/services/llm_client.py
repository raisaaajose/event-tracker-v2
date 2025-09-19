from __future__ import annotations

from app.model.llm import LLMExtractionInput, LLMExtractionOutput


async def extract_events(payload: LLMExtractionInput) -> LLMExtractionOutput:
    """Extract relevant events from emails using an LLM.

    TODO: Implement this function to call the actual LLM service.
    It should return LLMExtractionOutput with a list of ProposedEvent items.
    """
    # Placeholder no-op implementation
    return LLMExtractionOutput(events=[])
