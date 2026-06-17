"""
Marwa Chatbot — Intent Classification

Ollama LLM-based intent classification with keyword regex fallback.
Classifies customer messages into: book_appointment, check_status,
reschedule, cancel, ask_question, greeting, or unknown.
"""

import json
import re
import logging
from datetime import date, timedelta
from typing import List, Dict

import httpx

from .config import OLLAMA_BASE_URL, OLLAMA_MODEL
from .models import Intent, IntentResult
from .knowledge import SERVICE_KEYWORDS

logger = logging.getLogger("marwa-chatbot.classifier")

# ── Ollama Prompt ─────────────────────────────────────────────────────

INTENT_PROMPT = """You are an intent classifier for an auto repair shop chatbot.
Analyze the customer message and output ONLY a JSON object with this exact structure:
{"intent": "<intent_name>", "confidence": <0.0-1.0>, "entities": {}}

Intents:
- book_appointment: Customer wants to schedule a service/repair
- check_status: Customer asks about their appointment or car status
- reschedule: Customer wants to change their appointment time
- cancel: Customer wants to cancel their appointment
- ask_question: Customer asks about services, pricing, hours, etc.
- greeting: Just saying hello, no action needed
- unknown: Cannot determine intent

For book_appointment, extract entities if present:
  service_type: oil change, brake repair, engine diagnostics, tire services, ac repair, custom exhaust, general repair
  vehicle: year/make/model if mentioned (e.g., "2020 Honda Civic")
  preferred_date: date if mentioned (today, tomorrow, Monday, specific date)
  preferred_time: time if mentioned (morning, afternoon, 2pm, specific time)
  customer_name: if they introduce themselves
  customer_phone: if they provide a phone number

For check_status/reschedule/cancel, extract:
  customer_name: who they are
  appointment_reference: any reference number or date they mention

Message: {message}

JSON only, no other text:"""


# ── Ollama Classification ──────────────────────────────────────────────

async def classify_intent(
    message: str,
    conversation_history: List[Dict[str, str]] | None = None,
) -> IntentResult:
    """Use Ollama to classify the customer's intent and extract entities."""
    # Build context from recent history
    context = ""
    if conversation_history:
        recent = conversation_history[-4:]  # last 4 messages
        context = "\n".join(
            f"{'Customer' if m['role'] == 'user' else 'Bot'}: {m['content']}"
            for m in recent
        )

    prompt = INTENT_PROMPT.format(message=message)
    if context:
        prompt = f"Recent conversation:\n{context}\n\n{prompt}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 256},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()

        # Extract JSON from response (Ollama sometimes wraps in markdown)
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            parsed = json.loads(json_match.group(0))
            return IntentResult(
                intent=Intent(parsed.get("intent", "unknown")),
                confidence=parsed.get("confidence", 0.0),
                entities=parsed.get("entities", {}),
                raw_response=raw,
            )
        else:
            # Fallback: keyword-based classification
            return keyword_classify(message)

    except Exception as e:
        logger.warning(
            f"Ollama intent classification failed: {e}. "
            "Falling back to keyword classifier."
        )
        return keyword_classify(message)


# ── Keyword Fallback Classifier ───────────────────────────────────────

def keyword_classify(message: str) -> IntentResult:
    """Fallback rule-based intent classifier when Ollama is unavailable."""
    msg = message.lower().strip()

    # CANCEL — check first (before booking, which also matches "appointment")
    if re.search(
        r'\b(cancel|can\'t make it|won\'t.*make|need.*cancel)\b', msg
    ):
        return IntentResult(intent=Intent.CANCEL, confidence=0.8)

    # RESCHEDULE — check before booking
    if re.search(
        r'\b(reschedule|change.*(appointment|time|date)|'
        r'move.*(appointment|time)|different.*(day|time))\b',
        msg,
    ):
        return IntentResult(intent=Intent.RESCHEDULE, confidence=0.8)

    # STATUS — check before booking
    if re.search(
        r'\b(status|update|check.*(appointment|car|vehicle|repair|status)|'
        r'how.*(my|the).*(car|vehicle|repair|appointment|going)|'
        r'is.*(my|the).*(car|ready|done|fixed))\b',
        msg,
    ):
        return IntentResult(intent=Intent.CHECK_STATUS, confidence=0.8)

    # GREETING — short messages that are just hellos
    if re.search(
        r'^(hi|hello|hey|good morning|good afternoon|sup|yo)\b', msg
    ) and len(msg.split()) <= 3:
        return IntentResult(intent=Intent.GREETING, confidence=0.9)

    # BOOKING patterns
    book_patterns = [
        r'\b(book|schedule|set up|make.*appointment|'
        r'need.*(oil|brake|repair|service|fix|tire|ac|exhaust|diagnostic|check.*up|maintenance))\b',
        r'\b(want.*(to.*get|to.*have).*(oil|brake|repair|service|fix|tire|ac|exhaust))\b',
        r'\b(can i.*(bring|drop|come).*(car|vehicle|truck))\b',
        r'\b(i need.*(oil change|brake|repair|service|tune.up|maintenance))\b',
        r'\b(i\'d like.*(to.*(book|schedule|get|have)).*(oil|brake|repair|service))\b',
    ]
    for pattern in book_patterns:
        if re.search(pattern, msg):
            entities = {}

            # Extract service type
            for keyword, service in SERVICE_KEYWORDS.items():
                if keyword in msg:
                    entities["service_type"] = service
                    break

            # Extract vehicle
            vehicle_match = re.search(r'(\d{4})\s+([a-z]+)\s+([a-z]+)', msg)
            if vehicle_match:
                entities["vehicle"] = (
                    f"{vehicle_match.group(1)} "
                    f"{vehicle_match.group(2).title()} "
                    f"{vehicle_match.group(3).title()}"
                )

            # Extract date hints
            if "today" in msg:
                entities["preferred_date"] = date.today().isoformat()
            elif "tomorrow" in msg:
                entities["preferred_date"] = (
                    date.today() + timedelta(days=1)
                ).isoformat()

            return IntentResult(
                intent=Intent.BOOK, confidence=0.7, entities=entities
            )

    # QUESTION patterns
    if re.search(
        r'\b(how much|price|cost|hours|open|location|address|'
        r'what.*(do|is|are)|do you|can you)\b',
        msg,
    ):
        return IntentResult(intent=Intent.ASK_QUESTION, confidence=0.6)

    return IntentResult(intent=Intent.UNKNOWN, confidence=0.0)
