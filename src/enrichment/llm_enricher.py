"""LLM-based listing analysis using OpenAI's API.

Sends listing data to GPT-4o-mini and extracts structured enrichment
fields such as deal classification, urgency score, and more.
"""

import json
import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a real-estate analyst specializing in the Austin, TX rental market.
Analyze the provided listing and return a JSON object with EXACTLY these fields:

{
  "summary": "<2-3 sentence summary of the listing>",
  "urgency_score": <int 1-10, how urgent/time-sensitive this listing is>,
  "negotiability_score": <int 1-10, how negotiable the price seems>,
  "incentives": [<list of strings: any incentives like free month, discount, etc.>],
  "deal_classification": "<one of: STEAL, GOOD_DEAL, AVERAGE, OVERPRICED>",
  "outreach_suggestion": "<suggested message to send to the landlord/poster>",
  "listing_type": "<one of: apartment, sublease, roommate, lease_takeover>",
  "furnished": <true, false, or null if unknown>,
  "pets_allowed": <true, false, or null if unknown>,
  "bedrooms": <int or null if cannot be inferred>,
  "bathrooms": <float or null if cannot be inferred>
}

Rules:
- Return ONLY valid JSON. No markdown, no code fences, no extra text.
- Use null (not "null" or "None") for unknown values.
- urgency_score 10 = extremely urgent (e.g. move-in tomorrow, first come first served).
- negotiability_score 10 = highly negotiable (e.g. poster seems desperate, price dropped).
- deal_classification should reflect Austin market rates (~$1600/mo average for 1BR downtown).
- outreach_suggestion should be polite, specific, and reference details from the listing.
"""


def _build_user_message(listing: dict) -> str:
    """Format listing data into a readable prompt for the LLM."""
    parts = []
    field_labels = {
        "title": "Title",
        "body": "Description",
        "price": "Price",
        "address": "Address",
        "url": "URL",
        "source": "Source",
        "posted_at": "Posted",
        "bedrooms": "Bedrooms",
        "bathrooms": "Bathrooms",
        "sqft": "Square Feet",
    }
    for key, label in field_labels.items():
        value = listing.get(key)
        if value is not None and value != "":
            parts.append(f"{label}: {value}")

    # Include any extra keys not in the standard set
    for key, value in listing.items():
        if key not in field_labels and value is not None and value != "":
            parts.append(f"{key}: {value}")

    return "\n".join(parts)


def _empty_enrichment() -> dict:
    """Return a neutral enrichment dict used as a fallback."""
    return {
        "summary": None,
        "urgency_score": None,
        "negotiability_score": None,
        "incentives": [],
        "deal_classification": None,
        "outreach_suggestion": None,
        "listing_type": None,
        "furnished": None,
        "pets_allowed": None,
        "bedrooms": None,
        "bathrooms": None,
    }


async def enrich_listing(listing: dict) -> dict:
    """Send listing data to GPT-4o-mini and return structured enrichment fields.

    Returns a dict with enrichment keys (summary, urgency_score, etc.).
    Falls back to an empty enrichment dict if the API key is not configured
    or the API call fails for any reason.
    """
    if not settings.openai_api_key:
        logger.warning("OpenAI API key is not set; skipping LLM enrichment")
        return _empty_enrichment()

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    user_message = _build_user_message(listing)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=800,
        )

        raw_content = response.choices[0].message.content.strip()
        logger.debug("LLM raw response: %s", raw_content)

        enrichment = json.loads(raw_content)

        # Validate expected keys are present; fill missing ones with defaults
        defaults = _empty_enrichment()
        for key in defaults:
            if key not in enrichment:
                enrichment[key] = defaults[key]

        logger.info(
            "LLM enrichment complete: classification=%s, urgency=%s",
            enrichment.get("deal_classification"),
            enrichment.get("urgency_score"),
        )
        return enrichment

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        return _empty_enrichment()
    except Exception as exc:
        logger.error("LLM enrichment failed: %s", exc)
        return _empty_enrichment()
