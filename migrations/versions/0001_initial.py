"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "parsed_resumes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("parsed_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "normalized_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("skills_json", sa.JSON(), nullable=False),
        sa.Column("implied_skills_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "match_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(length=64), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_description_hash", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("matched_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parsing_ms", sa.Integer(), nullable=False),
        sa.Column("normalization_ms", sa.Integer(), nullable=False),
        sa.Column("matching_ms", sa.Integer(), nullable=False),
        sa.Column("error_log", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "unknown_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("raw_skill", sa.String(length=256), nullable=False),
        sa.Column("context", sa.Text(), nullable=False, server_default=""),
        sa.Column("flagged_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(length=256), nullable=False, unique=True),
        sa.Column("owner", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("rate_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("unknown_skills")
    op.drop_table("pipeline_runs")
    op.drop_table("match_results")
    op.drop_table("normalized_profiles")
    op.drop_table("parsed_resumes")
    op.drop_table("candidates")
