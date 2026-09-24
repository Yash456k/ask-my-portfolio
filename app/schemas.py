from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=700)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("history content is empty")
        return clean


UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class ClientContext(BaseModel):
    """Pseudonymous browser context recorded with each question (no raw identifiers)."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    visitor_id: str = Field(pattern=UUID_PATTERN, alias="visitorId")
    session_id: str = Field(pattern=UUID_PATTERN, alias="sessionId")
    timezone: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")
    language: str | None = Field(default=None, max_length=35, pattern=r"^[A-Za-z0-9-]+$")
    screen: str | None = Field(default=None, max_length=11, pattern=r"^\d{2,5}x\d{2,5}$")


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    question: str = Field(min_length=2, max_length=500)
    embedder: str = Field(min_length=2, max_length=80)
    model: str = Field(min_length=2, max_length=100)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=6)
    top_k: Literal[3, 5, 7] = Field(default=3, alias="topK")
    use_history: bool = Field(default=True, alias="useHistory")
    client: ClientContext | None = None

    @field_validator("client", mode="wrap")
    @classmethod
    def drop_invalid_client(cls, value, handler):
        # Logging context is optional: a malformed block must never block a question.
        try:
            return handler(value)
        except ValidationError:
            return None

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        clean = " ".join(value.split())
        if len(clean) < 2:
            raise ValueError("question is empty")
        return clean


class ActivityPeriod(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: date
    end: date


class ActivityCountDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    count: int = Field(ge=0)


class ActivityTokenDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date
    tokens: int = Field(ge=0)


class CodexActivity(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    total: int = Field(ge=0)
    lifetime_total: int = Field(ge=0, alias="lifetimeTotal")
    peak_daily_tokens: int = Field(ge=0, alias="peakDailyTokens")
    active_days: int = Field(ge=0, le=370, alias="activeDays")
    peak: ActivityCountDay | None
    days: list[ActivityTokenDay] = Field(max_length=370)


class GitHubActivity(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    username: str = Field(
        min_length=1,
        max_length=39,
        pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$",
    )
    total: int = Field(ge=0)
    active_days: int = Field(ge=0, le=370, alias="activeDays")
    peak: ActivityCountDay | None
    days: list[ActivityCountDay] = Field(max_length=370)


class ActivitySnapshot(BaseModel):
    """The complete public activity contract. Undeclared fields never leave the API."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    generated_at: datetime = Field(alias="generatedAt")
    period: ActivityPeriod
    codex: CodexActivity
    github: GitHubActivity
