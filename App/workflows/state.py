"""
Purpose:
    Typed LangGraph state carried through the intent classification /
    metadata extraction / validation node — a Pydantic model rather than
    a TypedDict, so the state itself is validated (types, defaults) the
    same way every other structured value in this codebase is
    (App/schemas/extraction.py's ExtractedFields uses the same approach).

Scope:
    State shape + validation only.

Does not handle:
    Any processing logic — see App/workflows/intent_node.py. LangGraph
    (1.x, as pinned implicitly by this project) accepts a Pydantic
    BaseModel directly as a StateGraph's state schema — nodes receive a
    validated IntentState instance when invoked through a compiled graph,
    and may return either a partial dict of changed fields or another
    IntentState instance.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class IntentState(BaseModel):
    user_query: str = ""
    intent: str | None = None
    username: str | None = None
    email: str | None = None
    employee_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    is_valid: bool = False
    error: str | None = None
