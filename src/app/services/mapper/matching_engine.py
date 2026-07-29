"""
matching_engine.py — Intelligent Table Matching Engine
======================================================
Matches Tableau datasource table names against Unity Catalog tables
using name similarity scoring. Table-level matching only (no column
comparison).

Uses Python's difflib.SequenceMatcher — no external packages needed.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional


@dataclass
class MatchSuggestion:
    """A suggested mapping from a Tableau table to a Databricks UC table."""
    tableau_table: str
    target_full_name: str       # catalog.schema.table
    confidence_score: float     # 0.0 - 1.0
    match_reason: str           # Human-readable explanation


def _clean_name(name: str) -> str:
    """Normalize a table name for comparison.

    Strips $, !, special chars, lowercases, splits into tokens.
    """
    cleaned = re.sub(r'[\$!].*$', '', name)  # Remove $ suffix and ! ranges
    cleaned = re.sub(r'[^a-zA-Z0-9_\s]', ' ', cleaned)  # Replace specials with space
    cleaned = cleaned.strip().lower()
    return cleaned


def _tokenize(name: str) -> List[str]:
    """Split a name into tokens for comparison."""
    cleaned = _clean_name(name)
    tokens = re.split(r'[_\s]+', cleaned)
    return [t for t in tokens if t]


def _sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_overlap(tokens_a: List[str], tokens_b: List[str]) -> float:
    """Jaccard-like overlap between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def compute_table_similarity(tableau_name: str, uc_table_name: str) -> float:
    """Compute similarity score between a Tableau table name and a UC table name.

    Combines:
      - 60% SequenceMatcher on cleaned names
      - 40% Token overlap (splits on _ and spaces)

    Returns: float 0.0 - 1.0
    """
    clean_tab = _clean_name(tableau_name)
    clean_uc = _clean_name(uc_table_name)

    # Exact match after cleaning
    if clean_tab == clean_uc:
        return 1.0

    seq_score = _sequence_similarity(clean_tab, clean_uc)

    tokens_tab = _tokenize(tableau_name)
    tokens_uc = _tokenize(uc_table_name)
    token_score = _token_overlap(tokens_tab, tokens_uc)

    return 0.6 * seq_score + 0.4 * token_score


def find_best_matches(
    tableau_table: str,
    uc_tables: List[Dict[str, str]],
    min_confidence: float = 0.3,
    max_results: int = 5,
) -> List[MatchSuggestion]:
    """Find the best UC table matches for a Tableau table name.

    Args:
        tableau_table: Original Tableau table name (e.g., 'Sheet1$')
        uc_tables: List of dicts with keys: catalog, schema, table, full_name
        min_confidence: Minimum score to include in results
        max_results: Maximum number of suggestions to return

    Returns:
        List of MatchSuggestion sorted by confidence descending
    """
    suggestions: List[MatchSuggestion] = []

    for uc in uc_tables:
        uc_name = uc.get("table", uc.get("name", ""))
        full_name = uc.get("full_name", f"{uc.get('catalog', '')}.{uc.get('schema', '')}.{uc_name}")

        score = compute_table_similarity(tableau_table, uc_name)

        if score >= min_confidence:
            if score >= 0.9:
                reason = f"Strong match: '{_clean_name(tableau_table)}' ≈ '{uc_name}' ({score:.0%})"
            elif score >= 0.6:
                reason = f"Partial match: '{_clean_name(tableau_table)}' ~ '{uc_name}' ({score:.0%})"
            else:
                reason = f"Weak match: '{_clean_name(tableau_table)}' → '{uc_name}' ({score:.0%})"

            suggestions.append(MatchSuggestion(
                tableau_table=tableau_table,
                target_full_name=full_name,
                confidence_score=round(score, 4),
                match_reason=reason,
            ))

    # Sort by confidence descending
    suggestions.sort(key=lambda s: s.confidence_score, reverse=True)
    return suggestions[:max_results]


def auto_match_datasources(
    tableau_tables: List[str],
    uc_tables: List[Dict[str, str]],
    min_confidence: float = 0.3,
) -> Dict[str, List[MatchSuggestion]]:
    """Auto-match all Tableau tables against UC tables.

    Args:
        tableau_tables: List of Tableau table names
        uc_tables: List of UC table dicts with full_name

    Returns:
        Dict mapping tableau_table -> list of MatchSuggestions
    """
    results: Dict[str, List[MatchSuggestion]] = {}

    for tab_table in tableau_tables:
        matches = find_best_matches(tab_table, uc_tables, min_confidence)
        results[tab_table] = matches

    return results
