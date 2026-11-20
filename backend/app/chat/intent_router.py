"""
chat/intent_router.py - decide the intent of a message BEFORE the LLM runs (owner: Piyush, M2).

The intent decides which tool the LLM may call in this turn, so policy retrieval never runs
for a weather-only question and weather never comes from the policy store.

Order of checks (first match wins):
  1. GREETING      only hello / thanks / bye words                          -> no tools
  2. OUT_OF_SCOPE  asks for the user's own records ("show my trips", "TKT-00003")
                   or asks Vera to act ("approve my claim", "book a hotel")  -> no tools
  3. keywords      weather words -> WEATHER, policy/how-to words -> POLICY, both -> POLICY_AND_WEATHER
  4. follow-up     short message with no signal ("and on the 27th?") inherits the previous
                   turn's intent in the same session
  5. embedding     similarity >= RAG_MIN_SIMILARITY to a policy chunk -> POLICY
  6. OUT_OF_SCOPE  anything else
Pure function: the embedding similarity is passed in, so tests need no model.
"""
import re
from typing import Callable

from app.core.config import get_settings
from app.schemas import ChatIntent, IntentDecision, ToolName

WEATHER_WORDS = re.compile(
    r"\b(weather|rain\w*|temperature\w*|forecast\w*|pack|packing|wear|umbrella|cold|hot|wind\w*|humid\w*|"
    r"sunny|snow\w*|climate|jacket|cloth\w*|degrees?|storm\w*|celsius|monsoon)\b", re.I)
POLICY_WORDS = re.compile(
    r"\b(expenses?|claim\w*|receipts?|limits?|polic\w*|reimburs\w*|tickets?|flag\w*|categor\w*|approv\w*|"
    r"reject\w*|trip requests?|travel requests?|traveldesk|threshold\w*|meals?|hotel|lodging|airfare|taxi|cab|"
    r"incidental\w*|invoices?|evidence|photo|allowed|deadline|per diem|vera|manager|complet\w*|"
    r"submit\w*|replacement|rupees|inr)\b|\bhow (do|can|should) (i|we)\b", re.I)
GREETING_ONLY = re.compile(
    r"^(hi|hello|hey|hiya|good (morning|afternoon|evening)|thanks?( you)?( so much| a lot)?|thank you|thx|"
    r"ok(ay)?|bye|goodbye|see you|cheers|great|cool)( vera)?[\s!.,]*$", re.I)
# "show my trips", "status of my ticket", "was my claim approved?", any TRP-/TKT-/EXP-/EVD- code
BUSINESS_DATA = re.compile(
    r"\b(TRP|TKT|EXP|EVD)-?\d+\b|"
    r"\b(show|list|check|see|view|open|fetch|get|find|track)\b.{0,20}\bmy\b.{0,20}\b(trips?|tickets?|expenses?|claims?|"
    r"receipts?|requests?|approvals?|status)\b|"
    r"\b(status of|was|were|is|are|has|have)\b.{0,10}\bmy\b.{0,20}\b(trips?|tickets?|expenses?|claims?|requests?)\b", re.I)
# asking Vera to DO something it never can
ACTION_REQUEST = re.compile(
    r"\b(can|could|will|would) you\b.{0,15}\b(approve|reject|book|submit|reimburse|edit|cancel|complete|pay)\b|"
    r"^\s*(please\s+)?(approve|reject|book|submit|reimburse|cancel|pay)\b|"
    r"\bis it safe\b|\bguarantee\b", re.I)
HOW_TO = re.compile(r"\bhow (do|can|should|to)\b|\bwhere (do|can) i\b", re.I)
FOLLOW_UP_MAX_WORDS = 12

TOOLS = {
    ChatIntent.POLICY: [ToolName.SEARCH_EXPENSE_POLICY],
    ChatIntent.WEATHER: [ToolName.GET_WEATHER_FORECAST],
    ChatIntent.POLICY_AND_WEATHER: [ToolName.SEARCH_EXPENSE_POLICY, ToolName.GET_WEATHER_FORECAST],
    ChatIntent.GREETING: [],
    ChatIntent.OUT_OF_SCOPE: [],
}


def _decision(intent: ChatIntent, reason: str) -> IntentDecision:
    return IntentDecision(intent=intent, allowed_tools=TOOLS[intent], reason=reason)


def route(message: str, previous_intent: ChatIntent | None = None,
          policy_similarity: Callable[[str], float] | None = None) -> IntentDecision:
    """Classify one (already masked) message. previous_intent is the last turn of THIS session."""
    text = message.strip()
    if GREETING_ONLY.match(text):
        return _decision(ChatIntent.GREETING, "greeting only")
    how_to = bool(HOW_TO.search(text))
    if not how_to and BUSINESS_DATA.search(text):
        return _decision(ChatIntent.OUT_OF_SCOPE, "business_data")
    if not how_to and ACTION_REQUEST.search(text):
        return _decision(ChatIntent.OUT_OF_SCOPE, "action_request")

    weather = sorted({m.lower() for m in WEATHER_WORDS.findall(text)})
    policy = sorted({m[0].lower() if isinstance(m, tuple) else m.lower() for m in POLICY_WORDS.findall(text)} - {""})
    if weather and policy:
        return _decision(ChatIntent.POLICY_AND_WEATHER, f"keywords: {', '.join(weather + policy)}")
    if weather:
        return _decision(ChatIntent.WEATHER, f"keywords: {', '.join(weather)}")
    if policy or how_to:
        return _decision(ChatIntent.POLICY, f"keywords: {', '.join(policy) or 'how-to'}")

    tool_intents = (ChatIntent.POLICY, ChatIntent.WEATHER, ChatIntent.POLICY_AND_WEATHER)
    if previous_intent in tool_intents and len(text.split()) <= FOLLOW_UP_MAX_WORDS:
        return _decision(previous_intent, f"inherited from previous turn ({previous_intent.value})")

    if policy_similarity is not None:
        try:
            score = policy_similarity(text)
        except Exception:          # noqa: BLE001 - embeddings down: just skip this signal
            score = 0.0
        if score >= get_settings().rag_min_similarity:
            return _decision(ChatIntent.POLICY, f"embedding similarity {score:.2f}")
    return _decision(ChatIntent.OUT_OF_SCOPE, "no_signal")
