"""The markets the engine has rules for, and what it does not model in each.

The engine is generic: equal weight, close to close, one cost per unit traded. A market
is "registered" only when someone has written down which of its trading frictions that
model leaves out, and every Result for that market carries the list. A market with no
entry is refused, so a spec for `sa` cannot return a Saudi-looking result from rules
nobody checked.

A-share frictions, as stated by the Shanghai Stock Exchange
(english.sse.com.cn/start/trading/mechanism/ and sse.com.cn/star/en/gettingstarted/
features/trading/, checked 2026-11-23): a share bought on one day is sold from the next
trading day; each board has a daily price limit; buy orders go in lots of 100 shares.
The limits differ by board and the sources disagree on some boards, so no percentage is
written here.
"""

from __future__ import annotations

FRICTIONS: dict[str, tuple[str, ...]] = {
    "cn_a": ("T+1 settlement", "daily price limits", "100-share board lots"),
}


def frictions(market: str) -> tuple[str, ...]:
    """What the engine does not model for `market`; refuses a market with no entry."""
    try:
        return FRICTIONS[market]
    except KeyError:
        raise ValueError(f"no market rules are registered for {market!r}; registered: {sorted(FRICTIONS)}") from None


def warning(market: str) -> str:
    return f"Not modelled for {market}: {', '.join(frictions(market))}. Results ignore these frictions."
