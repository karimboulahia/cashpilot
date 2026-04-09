"""Add conversation_contexts table.

Revision ID: 002_context
Revises: 001_initial
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "002_context"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_contexts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("last_intent", sa.String(50), nullable=True),
        sa.Column("last_item_name", sa.String(255), nullable=True),
        sa.Column("last_amount", sa.String(50), nullable=True),
        sa.Column("last_topic", sa.String(100), nullable=True),
        sa.Column("pending_action", sa.String(50), nullable=True),
        sa.Column("onboarding_step", sa.String(50), nullable=True),
        sa.Column("recent_messages", sa.JSON(), nullable=True),
        sa.Column("context_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_conversation_contexts_user_id", "conversation_contexts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_contexts_user_id", table_name="conversation_contexts")
    op.drop_table("conversation_contexts")
