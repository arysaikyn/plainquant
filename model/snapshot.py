"""A point-in-time view of the data. The engine reads nothing else.

Every lookup takes a date and answers with what was knowable on that date: a
fundamental becomes visible on its announcement date, never its report period, and
a name is in the universe only between the dates it was a member. A suspended name
carries its last price forward. Vendor adapters build one of these; the engine does
not know which vendor.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    version: str
    universe: str
    dates: list[str]  # trading days, ISO, ascending
    prices: dict[str, dict[str, float]]  # symbol -> date -> close
    # symbol -> [(announce_date, {fact key -> value or None})], ascending by date
    facts: dict[str, list[tuple[str, dict[str, float | None]]]]
    # symbol -> (first date a member, last date a member or None)
    membership: dict[str, tuple[str, str | None]]
    names: dict[str, str] = field(default_factory=dict)
    sectors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._price_dates = {s: sorted(p) for s, p in self.prices.items()}
        self._fact_dates = {s: [d for d, _ in rows] for s, rows in self.facts.items()}
        self._index = {d: i for i, d in enumerate(self.dates)}

    def universe_at(self, date: str) -> list[str]:
        return sorted(
            s for s, (first, last) in self.membership.items() if first <= date and (last is None or date <= last)
        )

    def price_at(self, symbol: str, date: str) -> float | None:
        """Last close on or before `date`; None before the first print."""
        keys = self._price_dates.get(symbol)
        if not keys:
            return None
        i = bisect_right(keys, date)
        return self.prices[symbol][keys[i - 1]] if i else None

    def fact_at(self, symbol: str, key: str, date: str) -> float | None:
        """From the latest report announced on or before `date`; None if it left the field out."""
        keys = self._fact_dates.get(symbol)
        if not keys:
            return None
        i = bisect_right(keys, date)
        return self.facts[symbol][i - 1][1].get(key) if i else None

    def offset(self, date: str, bars: int) -> str | None:
        """The trading day `bars` before `date` (`date` itself must be a trading day)."""
        i = self._index.get(date)
        if i is None:
            i = bisect_left(self.dates, date)
        return self.dates[i - bars] if 0 <= i - bars < len(self.dates) else None
