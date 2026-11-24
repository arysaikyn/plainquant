# Factors

The closed list a spec may name. The code owner is the registry in `model/factors.py`; this
page says what each id means. A factor id the registry does not list is refused by the
engine. Every factor reads only what was known on the date it is read (a price on or before
the date, a report published on or before it); tests pin that for each one.

`bars` are trading days of the snapshot. A name with too little history, or with a missing
price in the window, has no value for the factor and is not ranked on it: it is never ranked
on a zero.

| id | family | definition | reads |
|---|---|---|---|
| `debt_ratio` | fundamental | Total liabilities over total assets of the latest report published on or before the date. A proxy: it is not the interest-bearing debt ratio of a Sharia standard. | fact `debt_ratio` |
| `dividend_yield` | fundamental | Cash dividends announced in the last 365 days over the unadjusted close on the day of the latest announcement. It changes only when a dividend is announced. | fact `dividend_yield` |
| `momentum_6m` | momentum | Price change over the last 126 bars. | prices |
| `momentum_12_1` | momentum | Price change from 252 bars ago to 21 bars ago: the year, leaving out the last month. | prices |
| `return_1m` | reversal | Price change over the last 21 bars. Rank it ascending to buy recent losers. | prices |
| `volatility_60d` | volatility | Sample standard deviation of the last 60 daily returns. A day with no print carries the last price, so it counts as a zero return. | prices |

The family decides how the audit reads a spec (`model/audit.py`): the price block (momentum,
reversal, volatility) decays within days, the fundamental block within a year, and a spec
that reads only the price block is charged `priceOnly`.

Not built, and why: value (earnings, book), quality (return on equity) and size need fields
the first real data source has not been shown to carry. They wait for the first live fetch
(`docs/roadmap.md`, phase 1).
