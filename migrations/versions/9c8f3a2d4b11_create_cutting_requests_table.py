"""create cutting_requests table

Revision ID: 9c8f3a2d4b11
Revises: 2f6ccba8ffef
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c8f3a2d4b11"
down_revision: Union[str, None] = "2f6ccba8ffef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cutting_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),

        sa.Column("wood_type", sa.String(length=100), nullable=False),
        sa.Column("length_feet", sa.Float(), nullable=False),
        sa.Column("width_feet", sa.Float(), nullable=False),
        sa.Column("thickness_inches", sa.Float(), nullable=False),
        sa.Column("num_planks", sa.Integer(), nullable=False),

        sa.Column("purpose", sa.String(length=100), nullable=True),
        sa.Column("special_instructions", sa.Text(), nullable=True),
        sa.Column("preferred_date", sa.String(length=50), nullable=True),
        sa.Column("contact_phone", sa.String(length=15), nullable=False),

        sa.Column("quoted_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),

        sa.Column("razorpay_order_id", sa.String(), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),

        sa.Column(
            "status",
            sa.String(length=30),
            nullable=True,
            server_default="pending",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_cutting_requests_id",
        "cutting_requests",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cutting_requests_id",
        table_name="cutting_requests",
    )

    op.drop_table("cutting_requests")