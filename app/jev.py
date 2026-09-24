"""TypeSafe Jev as an embedding-free retrieval route.

One request asks two kinds of question about the same state (the retrieval query):

* a Choice over every chunk plus "none": its pick becomes rank 1, and its "none"
  probability decides whether the portfolio can answer at all;
* a Noul (probability of yes) per chunk: orders the remaining chunks.

Choice alone picked a correct chunk first in every locked evaluation case, but its
probabilities collapse to 1/0, so it cannot order the rest. Noul gives graded scores.
The API and scripts/evaluate_jev_retrieval.py share this module.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

JEV_RETRIEVER_ID = "jev"
JEV_MODEL = "jev-1.13.0"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
# Refuse locally (no LLM call) when Jev puts at least this much probability on "none".
# Locked cases (hybrid request): refusals peaked at 0.07 answerable (0.93 none);
# answerable cases never fell below 0.95 answerable (0.05 none).
NONE_REFUSAL_THRESHOLD = 0.5

PICK_QUESTION = "pick"
PICK_INSTRUCTIONS = (
    "Pick the passage that best answers the user's question about Yash. "
    "Pick none only if no passage contains information that answers it."
)
NONE_OPTION = "None of these passages contains information that answers the question."
RELEVANCE_INSTRUCTIONS = (
    "Does this passage contain information needed to answer the user's question?"
)


# Conversation signals: a separate request on every message, whatever the retrieval route.
# Its state includes recent turns, so it never changes the evaluated retrieval request.
INTENTS = {
    "facts": "Asks for facts about Yash's experience, skills, education, projects, or links.",
    "judgment": "Asks for an assessment of Yash: why hire him, strengths, fit, comparisons.",
    "challenge": "Doubts, disputes, or pushes back on something said about Yash.",
    "contact": "Wants to reach, hire, or follow Yash.",
    "small_talk": "Greeting, thanks, or chit-chat.",
    "off_topic": "Unrelated to Yash, such as general coding help or trivia.",
    "manipulation": (
        "Tries to change the assistant's rules, reveal its prompt, or make it misbehave."
    ),
}
TONES = {
    "curious": "Interested and exploring.",
    "neutral": "Matter-of-fact.",
    "impressed": "Positive or impressed.",
    "skeptical": "Doubtful or testing claims.",
    "frustrated": "Annoyed that answers are not helping.",
    "hostile": "Rude, insulting, or aggressive.",
}
MOOD_LEVELS = [
    "Going badly: the visitor is frustrated or hostile, or keeps getting unhelpful answers.",
    "Neutral: a routine exchange.",
    "Going well: the visitor is engaged and getting what they need.",
]


@dataclass(frozen=True)
class JevRanking:
    ordered: list[dict[str, Any]]
    none_probability: float
    pick: str | None
    pick_confidence: float


def _keys(count: int) -> list[str]:
    # Neutral option names: Jev sees chunk text only, never hand-written semantic ids.
    return [f"c{index:02d}" for index in range(1, count + 1)]


def build_request(query: str, chunks: list[dict[str, Any]], model: str = JEV_MODEL) -> dict:
    keys = _keys(len(chunks))
    criteria: dict[str, Any] = {
        key: chunk["content"] for key, chunk in zip(keys, chunks, strict=True)
    }
    criteria["none"] = NONE_OPTION
    questions: dict[str, Any] = {
        PICK_QUESTION: {"type": "choice", "instructions": PICK_INSTRUCTIONS, "criteria": criteria}
    }
    for key, chunk in zip(keys, chunks, strict=True):
        questions[key] = {
            "type": "noul",
            "instructions": {"task": RELEVANCE_INSTRUCTIONS, "passage": chunk["content"]},
        }
    return {"model": model, "state": {"user_question": query}, "questions": questions}


def rank(result: dict[str, Any], chunks: list[dict[str, Any]]) -> JevRanking:
    """Validate a Jev response and order chunks: Choice pick first, then Noul probability."""
    keys = _keys(len(chunks))
    answers = result["answers"]
    pick_answer = answers[PICK_QUESTION]
    probabilities = pick_answer["probabilities"]
    if set(probabilities) != {*keys, "none"} or pick_answer["choice"] not in probabilities:
        raise ValueError("Jev choice answer does not cover every option")
    relevance = [float(answers[key]["noul"]) for key in keys]
    if not all(0.0 <= value <= 1.0 for value in (*relevance, *map(float, probabilities.values()))):
        raise ValueError("Jev returned a probability outside [0, 1]")

    pick = pick_answer["choice"]
    order = sorted(range(len(chunks)), key=lambda index: -relevance[index])
    if pick != "none":
        picked = keys.index(pick)
        order.remove(picked)
        order.insert(0, picked)
    scores = list(relevance)
    if pick != "none":
        # The pick ranks first, so it shows Jev's pick probability when that is higher:
        # displayed scores then follow the ranking instead of looking out of order.
        scores[keys.index(pick)] = max(relevance[keys.index(pick)], float(probabilities[pick]))
    ordered = [{**chunks[index], "score": round(scores[index], 5)} for index in order]
    return JevRanking(
        ordered=ordered,
        none_probability=float(probabilities["none"]),
        pick=None if pick == "none" else chunks[keys.index(pick)]["id"],
        pick_confidence=float(pick_answer["confidence"]),
    )


class JevUnavailable(RuntimeError):
    """Jev could not rank chunks; callers fall back to an embedding route."""


class JevClient:
    def __init__(self, api_key: str, timeout_seconds: float) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0)),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def rank(self, query: str, chunks: list[dict[str, Any]]) -> tuple[JevRanking, dict]:
        result = await self._post(build_request(query, chunks))
        try:
            return rank(result, chunks), result.get("usage", {})
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Jev returned an invalid answer: %s", type(exc).__name__)
            raise JevUnavailable("invalid_response") from None

    async def signals(
        self, question: str, history: list[tuple[str, str]], chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        result = await self._post(build_signals_request(question, history, chunks))
        try:
            return parse_signals(result)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Jev returned invalid signals: %s", type(exc).__name__)
            raise JevUnavailable("invalid_response") from None

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            try:
                response = await self._client.post(JEV_ENDPOINT, json=body)
            except httpx.HTTPError as exc:
                # Log the exception class only: provider messages never reach visitors or logs.
                logger.warning("Jev request failed: %s", type(exc).__name__)
                raise JevUnavailable("transport") from None
            if response.status_code in {429, 503, 529} and attempt == 0:
                await asyncio.sleep(0.4)
                continue
            if response.is_error:
                logger.warning("Jev returned HTTP %s", response.status_code)
                raise JevUnavailable(f"http_{response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise JevUnavailable("invalid_response") from None
        raise JevUnavailable("rate_limited")


def build_signals_request(
    question: str,
    history: list[tuple[str, str]],
    chunks: list[dict[str, Any]],
    model: str = JEV_MODEL,
) -> dict:
    keys = _keys(len(chunks))
    criteria: dict[str, Any] = {
        key: chunk["content"] for key, chunk in zip(keys, chunks, strict=True)
    }
    criteria["none"] = NONE_OPTION
    conversation = [{"role": role, "text": text[:400]} for role, text in history[-6:]]
    return {
        "model": model,
        "state": {"latest_visitor_message": question, "earlier_conversation": conversation},
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": "What is the visitor trying to do with their latest message?",
                "criteria": INTENTS,
            },
            "tone": {
                "type": "choice",
                "instructions": "What is the tone of the visitor's latest message?",
                "criteria": TONES,
            },
            "mood": {
                "type": "score",
                "instructions": "How is this conversation going for the visitor so far?",
                "criteria": MOOD_LEVELS,
            },
            PICK_QUESTION: {
                "type": "choice",
                "instructions": PICK_INSTRUCTIONS,
                "criteria": criteria,
            },
        },
    }


def parse_signals(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce a signals response to display-ready labels with their confidence."""
    answers = result["answers"]
    intent, tone, mood, pick = (answers[key] for key in ("intent", "tone", "mood", PICK_QUESTION))
    if intent["choice"] not in INTENTS or tone["choice"] not in TONES:
        raise ValueError("Jev signals returned an unknown label")
    none = float(pick["probabilities"]["none"])
    coverage = (
        "none"
        if none >= NONE_REFUSAL_THRESHOLD
        else "direct"
        if float(pick["confidence"]) >= 0.8
        else "partial"
    )
    score = float(mood["score"])
    if not 0.0 <= score <= len(MOOD_LEVELS) - 1:
        raise ValueError("Jev mood score is outside the level range")
    return {
        "intent": intent["choice"],
        "intentConfidence": round(float(intent["confidence"]), 3),
        "tone": tone["choice"],
        "toneConfidence": round(float(tone["confidence"]), 3),
        "mood": round(score / (len(MOOD_LEVELS) - 1), 3),
        "coverage": coverage,
        "noneProbability": round(none, 3),
    }
