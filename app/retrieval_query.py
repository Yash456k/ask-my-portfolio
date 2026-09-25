from __future__ import annotations

import re
from collections.abc import Sequence

# Visitors ask from inside the chat, so "this project" or "this site" means the chat itself.
# Only questions that say so are rewritten; every other query is unchanged.
_SELF_REFERENCE = re.compile(r"\bthis (project|site|chat|app|website|portfolio)\b", re.IGNORECASE)
SELF_REFERENCE_NOTE = " (this means Ask my portfolio, the chat on Yash's portfolio site)"


def build_retrieval_query(
    question: str,
    history: Sequence[tuple[str, str]] = (),
    *,
    use_history: bool = True,
) -> str:
    """Resolve short follow-ups using recent user text, never assistant output."""
    if _SELF_REFERENCE.search(question):
        question += SELF_REFERENCE_NOTE
    if not use_history:
        return question
    prior_user_messages = [content for role, content in history[-4:] if role == "user"]
    if not prior_user_messages:
        return question
    context = "\n".join(prior_user_messages)
    return f"Previous user context:\n{context}\n\nCurrent question:\n{question}"
