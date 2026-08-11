"""Add canonical e-commerce domain tables

Revision ID: 20260810225719020
Revises: 20260731171240225
Create Date: 2026-08-10T22:57:19.020000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "20260810225719020"
down_revision: Union[str, None] = "20260731171240225"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Created in dependency order: regions, then customers and products, then
    # orders, then the rows that reference an order.
    op.create_table(
        "regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_regions_id"), "regions", ["id"], unique=False)
    op.create_index(op.f("ix_regions_name"), "regions", ["name"], unique=False)
    op.create_index(
        op.f("ix_regions_created_at"), "regions", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_regions_deleted_at"), "regions", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_regions_tenant_id"), "regions", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_regions_tenant_id_name", "regions", ["tenant_id", "name"], unique=False
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "external_identifier",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column("region_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_customers_id"), "customers", ["id"], unique=False)
    op.create_index(
        op.f("ix_customers_created_at"), "customers", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_customers_deleted_at"), "customers", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_customers_tenant_id"), "customers", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_customers_external_identifier"),
        "customers",
        ["external_identifier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customers_region_id"), "customers", ["region_id"], unique=False
    )
    op.create_index(
        "ix_customers_tenant_id_external_identifier",
        "customers",
        ["tenant_id", "external_identifier"],
        unique=False,
    )
    op.create_index(
        "ix_customers_tenant_id_region_id",
        "customers",
        ["tenant_id", "region_id"],
        unique=False,
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "stock_code", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True
        ),
        sa.Column("last_unit_price", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_id"), "products", ["id"], unique=False)
    op.create_index(
        op.f("ix_products_created_at"), "products", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_products_deleted_at"), "products", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_products_tenant_id"), "products", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_products_stock_code"), "products", ["stock_code"], unique=False
    )
    op.create_index(
        "ix_products_tenant_id_stock_code",
        "products",
        ["tenant_id", "stock_code"],
        unique=False,
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(
            "order_number", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("region_id", sa.Uuid(), nullable=True),
        sa.Column("ordered_at", sa.DateTime(), nullable=False),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"], unique=False)
    op.create_index(
        op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_orders_deleted_at"), "orders", ["deleted_at"], unique=False
    )
    op.create_index(op.f("ix_orders_tenant_id"), "orders", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_orders_order_number"), "orders", ["order_number"], unique=False
    )
    op.create_index(
        op.f("ix_orders_customer_id"), "orders", ["customer_id"], unique=False
    )
    op.create_index(op.f("ix_orders_region_id"), "orders", ["region_id"], unique=False)
    op.create_index(
        op.f("ix_orders_ordered_at"), "orders", ["ordered_at"], unique=False
    )
    op.create_index(
        "ix_orders_tenant_id_order_number",
        "orders",
        ["tenant_id", "order_number"],
        unique=False,
    )
    op.create_index(
        "ix_orders_tenant_id_ordered_at",
        "orders",
        ["tenant_id", "ordered_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_tenant_id_region_id_ordered_at",
        "orders",
        ["tenant_id", "region_id", "ordered_at"],
        unique=False,
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_id"), "order_items", ["id"], unique=False)
    op.create_index(
        op.f("ix_order_items_created_at"), "order_items", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_deleted_at"), "order_items", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_tenant_id"), "order_items", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False
    )
    op.create_index(
        op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False
    )
    op.create_index(
        "ix_order_items_tenant_id_order_id",
        "order_items",
        ["tenant_id", "order_id"],
        unique=False,
    )
    op.create_index(
        "ix_order_items_tenant_id_product_id",
        "order_items",
        ["tenant_id", "product_id"],
        unique=False,
    )

    op.create_table(
        "returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("region_id", sa.Uuid(), nullable=True),
        sa.Column("original_order_id", sa.Uuid(), nullable=True),
        sa.Column(
            "return_order_number",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("returned_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["original_order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_returns_id"), "returns", ["id"], unique=False)
    op.create_index(
        op.f("ix_returns_created_at"), "returns", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_returns_deleted_at"), "returns", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_returns_tenant_id"), "returns", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_returns_product_id"), "returns", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_returns_customer_id"), "returns", ["customer_id"], unique=False
    )
    op.create_index(
        op.f("ix_returns_region_id"), "returns", ["region_id"], unique=False
    )
    op.create_index(
        op.f("ix_returns_original_order_id"),
        "returns",
        ["original_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_returns_return_order_number"),
        "returns",
        ["return_order_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_returns_returned_at"), "returns", ["returned_at"], unique=False
    )
    op.create_index(
        "ix_returns_tenant_id_product_id",
        "returns",
        ["tenant_id", "product_id"],
        unique=False,
    )
    op.create_index(
        "ix_returns_tenant_id_returned_at",
        "returns",
        ["tenant_id", "returned_at"],
        unique=False,
    )


def downgrade() -> None:
    # Dropped in reverse dependency order.
    op.drop_table("returns")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("regions")
