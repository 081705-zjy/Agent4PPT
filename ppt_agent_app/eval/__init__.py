"""Deterministic + codex-graded evaluation for a generated PPT project.

Run once per project version to get repeatable scores. See eval.cli for CLI.
"""

from .deterministic import (
    score_outline_structure,
    score_source_distribution,
    score_retrieval_match,
    score_timing,
    run_all_deterministic,
)

__all__ = [
    "score_outline_structure",
    "score_source_distribution",
    "score_retrieval_match",
    "score_timing",
    "run_all_deterministic",
]
