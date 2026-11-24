"""The markets the engine has rules for: what it models, and what it does not.

The engine is generic: equal weight, fill at the close of the day after the ranking, one
cost per unit traded. A market is registered only when someone has written down its tax and
which of its trading frictions the model leaves out, and every Result for that market
carries the list. A market with no entry is refused, so a spec for `sa` cannot return a
Saudi-looking result from rules nobody checked.

A-share, as stated by the Shanghai Stock Exchange (english.sse.com.cn/start/trading/
mechanism/ and sse.com.cn/star/en/gettingstarted/features/trading/, checked 2026-11-23): a
share bought on one day is sold from the next trading day; each board has a daily price
limit; buy orders go in lots of 100 shares. The limits differ by board and the sources
disagree on some boards, so no percentage is written here.

Daily price limit, as stated by the Shenzhen Stock Exchange (szse.cn/English/services/trading/
tradOverview/ and its ChiNext rule PDF; China Daily 2020-08-18; checked 2026-11-24): 10% on
the main board; 20% on ChiNext from 2020-08-24. The 20% on the STAR Market (688) is
reported by the same press as the model for ChiNext; its own rule page was not read. The 5% for
ST names was not confirmed and is not modelled, nor is the five-day free window of new
listings.

A-share stamp duty is charged on the seller only. It was 0.1% and became 0.05% from
2023-08-28 (HKEX circular CT13723B, China Daily 2023-08-28, China Briefing on MOF
announcement 2023 No.39, checked 2026-11-23). A change after 2023 was not checked.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketRules:
    frictions: tuple[str, ...]  # what the engine does not model
    # Tax on the value sold, as (first day in force, rate), ascending by day.
    sell_tax: tuple[tuple[str, float], ...]
    # Daily price limit as (symbol prefixes, first day in force, limit); the last match wins.
    # A symbol that matches no row has no limit.
    limits: tuple[tuple[tuple[str, ...], str, float], ...] = ()


MARKETS: dict[str, MarketRules] = {
    "cn_a": MarketRules(
        frictions=("T+1 settlement", "the 5% limit of ST names", "100-share board lots"),
        sell_tax=(("0000-01-01", 0.001), ("2023-08-28", 0.0005)),
        limits=(
            (("60", "00"), "0000-01-01", 0.10),
            (("688",), "0000-01-01", 0.20),
            (("300", "301"), "0000-01-01", 0.10),
            (("300", "301"), "2020-08-24", 0.20),
        ),
    ),
}


def rules(market: str) -> MarketRules:
    """The rules for `market`; refuses a market with no entry."""
    try:
        return MARKETS[market]
    except KeyError:
        raise ValueError(f"no market rules are registered for {market!r}; registered: {sorted(MARKETS)}") from None


def sell_tax_rate(market: str, day: str) -> float:
    """The tax rate on a sale made on `day`."""
    rate = 0.0
    for first, value in rules(market).sell_tax:
        if first <= day:
            rate = value
    return rate


def price_limit(market: str, symbol: str, day: str) -> float | None:
    """The daily price limit for `symbol` on `day` as a fraction, or None when it has none."""
    limit = None
    for prefixes, first, value in rules(market).limits:
        if first <= day and symbol.startswith(prefixes):
            limit = value
    return limit


def warning(market: str) -> str:
    """The note every Result for `market` starts with."""
    return (
        f"Not modelled for {market}: {', '.join(rules(market).frictions)}. Results ignore these frictions. "
        "A name with no price on the fill day is treated as suspended: it is not bought and not sold. "
        "A name that closes at its daily limit on the fill day (within 0.5 points) cannot be bought at the up limit or sold at the down limit. "
        "Stamp duty on sales is charged at the rate in force on the fill day."
    )
