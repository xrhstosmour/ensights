"""Response schemas for the market basket endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class AssociationRuleRow(BaseSchema):
    """One association rule from a stored mining run."""

    run_identifier: str
    algorithm: str
    antecedents: list[str] = Field(default_factory=list)
    consequents: list[str] = Field(default_factory=list)
    antecedent_descriptions: list[str] = Field(default_factory=list)
    consequent_descriptions: list[str] = Field(default_factory=list)
    support: float = 0.0
    confidence: float = 0.0
    lift: float = Field(
        default=0.0,
        description=(
            "Confidence divided by the consequent's own support. Above 1.0 "
            "means the two sides co-occur more than chance would predict."
        ),
    )
    computed_at: datetime


class MiningRunAccepted(BaseSchema):
    """Acknowledgement that a mining run has been queued."""

    task_id: str
    status: str = "queued"
