"""
Conversation rewrite module for contextual follow-up questions.

Resolves pronouns and references across turns into standalone queries.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger("edocs.rag.rewrite")


def rewrite_question(
    message: str,
    history: List[dict] | None = None,
    llm_client: Optional[object] = None,
) -> str:
    """
    Rewrite the user's latest message into a standalone question.
    If history is empty or message is already standalone, return it unchanged.
    """
    if not history:
        return message.strip()

    # If message is long enough and contains key nouns, it is likely already standalone
    msg = message.strip()
    words = msg.lower().split()
    pronouns = {"it", "its", "that", "this", "they", "them", "these", "those"}
    has_pronoun = any(p in words for p in pronouns)

    if not has_pronoun and len(words) >= 6:
        return msg

    # If LLM client is available, call rewrite prompt
    if llm_client is not None and hasattr(llm_client, "generate"):
        try:
            history_text = "\n".join(
                f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-4:]
            )
            prompt = (
                f"Rewrite the user's latest message into ONE standalone question that can be understood "
                f"without the conversation. Keep all Symitar terms, identifiers, and numbers exactly as written. "
                f"Output only the standalone question.\n\n"
                f"Conversation:\n{history_text}\n\n"
                f"Latest message: {msg}\nStandalone question:"
            )
            rewritten = llm_client.generate(prompt)
            if rewritten and len(rewritten.strip()) > 3:
                return rewritten.strip()
        except Exception as e:
            logger.warning("LLM rewrite failed (%s), using rule-based resolution", e)

    # Heuristic fallback: combine last user topic with follow-up
    last_user_turn = next(
        (h.get("content", "") for h in reversed(history) if h.get("role") == "user"), ""
    )
    if last_user_turn and has_pronoun:
        return f"{last_user_turn} ({msg})"

    return msg
