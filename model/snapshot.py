"""A point-in-time view of the data. The engine reads nothing else.

Every lookup takes a date and answers with what was knowable on that date: a
fundamental becomes visible on its announcement date, never its report period, and
a name is in the universe only between the dates it was a member. A suspended name
carries its last price forward. Vendor adapters build one of these; the engine does
not know which vendor.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    version: str
    universe: str
    market: str  # the venue the data comes from: cn_a, hk, us or sa
    dates: list[str]  # trading days, ISO, ascending
    prices: dict[str, dict[str, float]]  # symbol -> date -> close
    # symbol -> [(announce_date, {fact key -> value or None})], ascending by date
    facts: dict[str, list[tuple[str, dict[str, float | None]]]]
    # symbol -> intervals [(first date a member, last date a member or None)]; a name can leave and return
    membership: dict[str, list[tuple[str, str | None]]]
    names: dict[str, str] = field(default_factory=dict)
    sectors: dict[str, str] = field(default_factory=dict)
    # Known defects of this data, in plain sentences. Every Result run on it repeats them.
    limitations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._price_dates = {s: sorted(p) for s, p in self.prices.items()}
        self._fact_dates = {s: [d for d, _ in rows] for s, rows in self.facts.items()}
        self._index = {d: i for i, d in enumerate(self.dates)}

    def universe_at(self, date: str) -> list[str]:
        return sorted(
            s
            for s, intervals in self.membership.items()
            if any(first <= date and (last is None or date <= last) for first, last in intervals)
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

    def trailing(self, date: str, bars: int) -> list[str] | None:
        """The `bars` + 1 trading days ending on the last trading day on or before `date`;
        None when the data starts later than that."""
        end = bisect_right(self.dates, date)
        return self.dates[end - bars - 1 : end] if end - bars - 1 >= 0 else None
