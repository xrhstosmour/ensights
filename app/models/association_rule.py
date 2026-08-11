"""Persisted results of frequent itemset mining.

Mining a full retail history is expensive, and the results are read far more
often than they are produced, so runs are materialised rather than recomputed
per request. Both tables record the parameters that produced them, because a
support threshold changes what "frequent" means and a rule is meaningless
without it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON
from sqlalchemy import Column
from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseModel


class FrequentItemset(BaseModel, table=True):
    """An itemset that meets the support threshold of a mining run.

    Attributes:
        id: UUID primary key
        run_identifier: Groups every row produced by one mining run
        algorithm: Algorithm that produced the run, apriori or fpgrowth
        minimum_support: Support threshold the run was executed with
        items: Stock codes forming the itemset
        item_count: Size of the itemset, stored so queries can filter by it
        support: Fraction of baskets containing the itemset
        computed_at: When the run executed
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "frequent_itemsets"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index(
            "ix_frequent_itemsets_tenant_id_run_identifier",
            "tenant_id",
            "run_identifier",
        ),
    )

    run_identifier: str = Field(nullable=False, index=True, max_length=64)
    algorithm: str = Field(nullable=False, max_length=32)
    minimum_support: float = Field(nullable=False)
    items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    item_count: int = Field(nullable=False, index=True)
    support: float = Field(nullable=False, index=True)
    computed_at: datetime = Field(nullable=False, index=True)


class AssociationRule(BaseModel, table=True):
    """A rule derived from the frequent itemsets of a mining run.

    Lift is the column that matters for interpretation. Support and confidence
    alone will happily promote a rule whose consequent is simply popular;
    lift above one is what says the two sides actually co-occur more than
    chance would predict.

    Attributes:
        id: UUID primary key
        run_identifier: Groups every row produced by one mining run
        algorithm: Algorithm that produced the run
        antecedents: Stock codes on the left-hand side
        consequents: Stock codes on the right-hand side
        antecedent_descriptions: Human-readable left-hand side
        consequent_descriptions: Human-readable right-hand side
        support: Fraction of baskets containing both sides
        confidence: Probability of the consequent given the antecedent
        lift: Confidence divided by the consequent's own support
        computed_at: When the run executed
        tenant_id: Organization that owns this record
        created_at: When the record was created
        updated_at: When the record was last modified
        deleted_at: Soft delete timestamp
    """

    __tablename__ = "association_rules"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index(
            "ix_association_rules_tenant_id_run_identifier",
            "tenant_id",
            "run_identifier",
        ),
        Index("ix_association_rules_tenant_id_lift", "tenant_id", "lift"),
    )

    run_identifier: str = Field(nullable=False, index=True, max_length=64)
    algorithm: str = Field(nullable=False, max_length=32)
    antecedents: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    consequents: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    antecedent_descriptions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    consequent_descriptions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    support: float = Field(nullable=False, index=True)
    confidence: float = Field(nullable=False, index=True)
    lift: float = Field(nullable=False, index=True)
    computed_at: datetime = Field(nullable=False, index=True)
