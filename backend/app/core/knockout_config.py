"""Knockout stage configuration for the 2026 FIFA World Cup.

Stage classification is inferred from kickoff dates because The Odds API does
not return round metadata. Update KNOCKOUT_DATE_WINDOWS once the official 2026
schedule is confirmed (dates below are based on current planning).
"""
from __future__ import annotations

from datetime import date, datetime, timezone


# Maps stage label → (first kickoff date, last kickoff date) inclusive, UTC.
KNOCKOUT_DATE_WINDOWS: dict[str, tuple[date, date]] = {
    "round_of_32":  (date(2026, 6, 28), date(2026, 7,  3)),
    "round_of_16":  (date(2026, 7,  4), date(2026, 7,  9)),
    "quarter_final": (date(2026, 7, 10), date(2026, 7, 14)),
    "semi_final":   (date(2026, 7, 15), date(2026, 7, 18)),
    "third_place":  (date(2026, 7, 18), date(2026, 7, 18)),
    "final":        (date(2026, 7, 19), date(2026, 7, 19)),
}

# Default scoring_basis assigned to newly imported knockout matches.
KNOCKOUT_SCORING_BASIS: dict[str, str] = {
    stage: "ninety_minutes_extra_time_penalties"
    for stage in KNOCKOUT_DATE_WINDOWS
}

# Keywords that identify placeholder / TBD team names returned by the provider.
_TBD_KEYWORDS = frozenset({"tbd", "tba", "winner", "loser", "qualif", "runner", "1st", "2nd"})


def infer_stage(kickoff: datetime) -> str:
    """Infer the match stage from its kickoff datetime. Returns 'group' as default."""
    d = kickoff.astimezone(timezone.utc).date() if kickoff.tzinfo else kickoff.date()
    for stage, (start, end) in KNOCKOUT_DATE_WINDOWS.items():
        if start <= d <= end:
            return stage
    return "group"


def is_placeholder(name: str) -> bool:
    """Return True if the team name looks like a TBD / qualifier placeholder."""
    lower = name.lower()
    return any(kw in lower for kw in _TBD_KEYWORDS)
