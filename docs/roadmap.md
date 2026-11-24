# Roadmap

What is left to finish the product, in the order it is done. Product scope is in
`product.md`; the trust boundary and what is not built is in `architecture.md`. This file
owns the phases, their exit criteria and the decisions taken. Status lives here and
nowhere else.

## Done means

1. China has a real snapshot, the data checks pass, and the limits of the data ship with every result.
2. The engine models fill timing, tradability and costs, and the audit has a measured false-positive rate.
3. The Sharia standard is named and checked against a public methodology, runs on real inputs, and matches a public list.
4. A second market (Saudi Arabia) has a real run. This depends on a data licence.
5. A question in Arabic, Chinese or English becomes rules, a result and an explanation; advice and orders are refused; a result can be reproduced from its receipt.
6. No screen reads mock data unless it says it is a demo, and the duplicated facts in `web/` are gone.
7. CI covers the engine, the agent, the data builder, the backend, the web app and e2e.
8. Each fact has one owner and no document is out of date.

## Decisions taken (2026-11-23)

- The AI tab's main path is `agent/`. Vibe-Trading stays as a "research assistant" and is labelled untrusted.
- Local first. Hosting waits until the data licences allow showing results.
- Model provider: the Anthropic API. The key belongs to the user and stays in `backend/`; `complete()` can be swapped.
- No sub-agents. Work is done in the session; research uses web search. If an agent is ever used, it gets a written packet (goal, must read, must not read, output, stop condition), it is read-only, and it only inventories; the main session judges. The model of a sub-agent cannot be pinned in this environment.
- Fill timing is an engine rule, not a spec field: rank at the close of the rebalance day, fill at the close of the next trading day.

## Phases

| # | Phase | Status | Exit criterion |
|---|---|---|---|
| 1 | Real data | blocked | A real snapshot passes the data checks and `/run` shows a real result with its limits. Blocked on the user running the first fetch, or allowing it. |
| 2 | Engine is trustworthy on real data | in progress | Fill lag, tradability and costs are modelled and tested; the audit false-positive rate is a number; run time is a number. |
| 3 | Sharia that works | not started | `compliant_only` returns a non-empty real result that matches a public list on at least 30 names. |
| 4 | Saudi Arabia | blocked | A real `sa` run. Blocked on a data licence. |
| 5 | Agent live | not started | Three languages from the UI to a result and an explanation; eval numbers recorded; reproduction works. |
| 6 | Other screens read results | not started | No screen reads mock data unless labelled. The user picks the plan first. |
| 7 | Product completeness | not started | Disclaimers reviewed, warnings coded and translated, refresh job, runbook. Licence and regulatory questions answered. |
| 8 | Release hygiene | not started | e2e and the design gate run in CI; deprecated dependencies replaced. |

## Tasks

**1 Real data.** Fix the field names the first live response shows. Fetch the full CSI 300 for 2019 to 2024. Check every sentence of the builder's `LIMITATIONS` against the response. Test whether `query_hs300_stocks(date=...)` returns the historical list (the parameter exists in the source; the behaviour is unconfirmed) and, if so, build point-in-time membership. Add a snapshot check command (calendar coverage, price gaps, jumps after adjustment, publication-date spread, names with no report). Reconcile the equal-weight return with the published index return and write the tolerance down.

**2 Engine.** Done: fill lag (rank at t, fill at t+1), the look-ahead tests for prices and for data after the last fill, a measured run time. To do: tradability (limit up and down, suspension, ST, delisting) from verified exchange rules, one-sided costs, a permutation test for the audit and the trial count for a deflated Sharpe, a factor library of about twelve factors in `docs/factors.md`.

**3 Sharia.** Name the standard from a public methodology (MSCI Islamic, S&P Shariah, AAOIFI). Replace the current caps, whose source is not confirmed, with the checked ones, in the engine only. Choose real inputs (interest-bearing debt, deposits and cash, interest income, receivables, total assets, average market cap). Write the adapter. Compare with a public index list.

**4 Saudi Arabia.** Ask the Saudi Exchange and Argaam in writing about licence terms. Check the market rules from two sources each (price limit, settlement, lot, trading days, Ramadan hours). Add `sa` to `model/markets.py`. Write the adapter. Run one spec on `cn_a` and on `sa`.

**5 Agent.** `POST /api/engine/ask`: question, spec, run, claims. Declare `jsonschema` in `backend/pyproject.toml`. Cache runs on spec hash and data version. Implement `complete()`. Grow the eval to about 40 questions in three languages, including advice, orders, guarantees and injected instructions. Proposed targets: valid specs 95%, correct 80%, refusals 100%. Render claims in the web app. Add `python3 -m model verify` and a reproduce control on `/run`; archive snapshots by data version.

**6 Screens.** If the user chooses a rebuild: add the exclusion funnel, the gross curve, the trial count and the Sharia check detail to the Result; store saved runs; rebuild `StrategyDetail`, the Screener, compare and report on results; delete the TypeScript copies and `test_shared_facts.py`; derive the e2e route lists from `screens.ts`.

**7 Completeness.** Disclaimer review; regulatory advice for Saudi Arabia and China; coded warnings with translations; a daily refresh job and a snapshot retention rule; a runbook.

**8 Hygiene.** e2e on system Chrome in CI; the design gate in CI; move from `RefResolver` to `referencing`; confirm the `polish` "Stop" failure on system Chrome (it also fails on the first commit of `main` here); licence file and dependency audit.

## Order

1, then the fill, tradability and cost work of phase 2, then 5, then 3, then the rest of 2, then 6, then 4, then 7, then 8. Phase 5 comes early because it is the first time the product's main line (ask, rules, backtest, explanation) works from end to end. Licence enquiries for phases 3 and 4 start now, because they take longest.

## Stop points

- S1: real data in `/run`.
- S2: the main line works end to end.
- S3: Sharia on real inputs.
- S4: phases 6 and 7 done.

## Not in scope

Orders, brokers, custody, advice, price prediction, intraday, native mobile.
