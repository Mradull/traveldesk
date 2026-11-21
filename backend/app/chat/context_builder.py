"""
chat/context_builder.py - build the messages the LLM sees for one turn (owner: Piyush, M2).

Blocks (spec "Context and memory"):
  system prompt (+ today's date, + this session's rolling summary)
  recent history: last 8 turns of THIS session, human and Vera text verbatim; tool results
                  in full for the last 2 turns, a one-line digest for older ones
  current message (already masked)
No other session, no business data and no ids are ever added. Tool results are attached to
Vera's message text (not as tool messages), which every provider accepts even without tools.
"""
from datetime import date

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.ai import prompts
from app.chat.memory import Turn, tool_digest
from app.schemas import ContextBundle, ToolName

HISTORY_TOKEN_BUDGET = 3000      # of the 6,000-token CHAT_CONTEXT_TOKEN_BUDGET
FULL_TOOL_TURNS = 2


def _tokens(text: str) -> int:
    """Rough estimate: ~4 characters per token (good enough for budgeting)."""
    return len(text) // 4 + 1


def build(turns: list[Turn], summary: str | None, user_message: str, allowed_tools: list[ToolName],
          today: date) -> ContextBundle:
    """Assemble the context of one turn from this session's turns only."""
    history: list[dict] = []
    for i, t in enumerate(turns):
        recent = i >= len(turns) - FULL_TOOL_TURNS
        data = [f"[{name} result: {content}]" if recent else f"[{tool_digest(name, content)}]"
                for name, content in t.tool_outputs]
        history.append({"role": "human", "content": t.human})
        history.append({"role": "ai", "content": "\n".join([t.ai, *data])})
    # keep the newest turns that fit the history budget (drop oldest pairs first)
    while history and sum(_tokens(m["content"]) for m in history) > HISTORY_TOKEN_BUDGET:
        history = history[2:]
    system = prompts.build_system_prompt(today, summary)
    total = _tokens(system) + sum(_tokens(m["content"]) for m in history) + _tokens(user_message)
    return ContextBundle(system_prompt=system, session_summary=summary, history=history,
                         user_message=user_message, allowed_tools=allowed_tools, estimated_tokens=total)


def to_messages(bundle: ContextBundle) -> list[BaseMessage]:
    """ContextBundle -> LangChain messages."""
    messages: list[BaseMessage] = [SystemMessage(bundle.system_prompt)]
    for m in bundle.history:
        messages.append(HumanMessage(m["content"]) if m["role"] == "human" else AIMessage(m["content"]))
    messages.append(HumanMessage(bundle.user_message))
    return messages

