"""Add frequent itemset and association rule result tables

Revision ID: 20260811070937489
Revises: 20260810225719020
Create Date: 2026-08-11T07:09:37.489000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "20260811070937489"
down_revision: Union[str, None] = "20260810225719020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mining runs are materialised rather than recomputed per request, so both
    # tables carry the parameters that produced them: a support value is
    # meaningless without the threshold it was mined at.
    op.create_table(
        "frequent_itemsets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "run_identifier",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "algorithm", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False
        ),
        sa.Column("minimum_support", sa.Float(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("support", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_frequent_itemsets_id"), "frequent_itemsets", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_frequent_itemsets_created_at"),
        "frequent_itemsets",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_deleted_at"),
        "frequent_itemsets",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_tenant_id"),
        "frequent_itemsets",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_run_identifier"),
        "frequent_itemsets",
        ["run_identifier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_item_count"),
        "frequent_itemsets",
        ["item_count"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_support"),
        "frequent_itemsets",
        ["support"],
        unique=False,
    )
    op.create_index(
        op.f("ix_frequent_itemsets_computed_at"),
        "frequent_itemsets",
        ["computed_at"],
        unique=False,
    )
    op.create_index(
        "ix_frequent_itemsets_tenant_id_run_identifier",
        "frequent_itemsets",
        ["tenant_id", "run_identifier"],
        unique=False,
    )

    op.create_table(
        "association_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "run_identifier",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "algorithm", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False
        ),
        sa.Column("antecedents", sa.JSON(), nullable=True),
        sa.Column("consequents", sa.JSON(), nullable=True),
        sa.Column("antecedent_descriptions", sa.JSON(), nullable=True),
        sa.Column("consequent_descriptions", sa.JSON(), nullable=True),
        sa.Column("support", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("lift", sa.Float(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_association_rules_id"), "association_rules", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_association_rules_created_at"),
        "association_rules",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_deleted_at"),
        "association_rules",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_tenant_id"),
        "association_rules",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_run_identifier"),
        "association_rules",
        ["run_identifier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_support"),
        "association_rules",
        ["support"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_confidence"),
        "association_rules",
        ["confidence"],
        unique=False,
    )
    op.create_index(
        op.f("ix_association_rules_lift"), "association_rules", ["lift"], unique=False
    )
    op.create_index(
        op.f("ix_association_rules_computed_at"),
        "association_rules",
        ["computed_at"],
        unique=False,
    )
    op.create_index(
        "ix_association_rules_tenant_id_run_identifier",
        "association_rules",
        ["tenant_id", "run_identifier"],
        unique=False,
    )
    op.create_index(
        "ix_association_rules_tenant_id_lift",
        "association_rules",
        ["tenant_id", "lift"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("association_rules")
    op.drop_table("frequent_itemsets")
