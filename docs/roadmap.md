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
| 1 | Real data | partly done | A real snapshot passes `data.check` and `/ai` shows a real result with its limits. Decided 2026-11-24: the demo is a 20-name real sample, labelled as a sample in every Result. The full fetch failed twice (killed for memory; then the source refused connections) and is not run; the builder now resumes from `OUT.partial`. |
| 2 | Engine is trustworthy on real data | in progress | Fill lag, tradability and costs are modelled and tested; the audit false-positive rate is a number; run time is a number. |
| 3 | Sharia that works | not started | `compliant_only` returns a non-empty real result that matches a public list on at least 30 names. |
| 4 | Saudi Arabia | blocked | A real `sa` run. Blocked on a data licence. |
| 5 | Agent live | in progress | Three languages from the UI to a result and an explanation; eval numbers recorded; reproduction works. The route, the screen and their tests exist; no key has been used yet. |
| 6 | Other screens read results | not started | No screen reads mock data unless labelled. The user picks the plan first. |
| 7 | Product completeness | not started | Disclaimers reviewed, warnings coded and translated, refresh job, runbook. Licence and regulatory questions answered. |
| 8 | Release hygiene | not started | e2e and the design gate run in CI; deprecated dependencies replaced. |

## Tasks

**1 Real data.** Done: the field names are confirmed; the debt-ratio defect found and handled; the limitations checked against the response; historical membership works and is built; `data.check` exists; a 20-name trial ran end to end. To do (waits for the source to answer again): run the full fetch with `python3 -m data.baostock_source --out data/raw/csi300`; check it; reconcile the equal-weight return with the published CSI 300 return and write the tolerance down; decide which of the fields seen but not used (`roeAvg`, `totalShare`, per-day `pctChg` and `isST`) to fetch, then fetch once more.

**2 Engine.** Done: daily price limits on the fill day (10% main board, 20% ChiNext from 2020-08-24, 20% STAR), fill lag (rank at t, fill at t+1), the look-ahead tests for prices and for data after the last fill, a measured run time, suspension as "no price on the fill day", the seller's stamp duty by date, a significance gate on the audit with a measured noise false-positive rate, and four price factors in `docs/factors.md`. To do: ST (the 5% limit and the flag need per-day data) and delisting, the trial count for a deflated Sharpe (it needs a stored run log, so it waits for phase 6), and the value, quality and size factors once real fields are known.

**3 Sharia.** Checked 2026-11-24 from search results, not from the standards' own text: AAOIFI Standard 21 caps interest-bearing debt and interest-bearing deposits at 30% of market capitalisation and impure income at 5%; MSCI Islamic uses total debt over total assets at 33.33% in its Index Series (a 70% proposal was seen, adoption not confirmed); the 33% receivables cap seems to be an older Dow Jones rule that AAOIFI dropped. So `model/sharia.py` mixes standards, and its `debt_ratio` (liabilities over assets) is a proxy for neither. Baostock has no interest-bearing debt or market-cap ratios, so a real A-share Sharia run is not meaningful. Name the standard from a public methodology (MSCI Islamic, S&P Shariah, AAOIFI). Replace the current caps, whose source is not confirmed, with the checked ones, in the engine only. Choose real inputs (interest-bearing debt, deposits and cash, interest income, receivables, total assets, average market cap). Write the adapter. Compare with a public index list.

**4 Saudi Arabia.** Ask the Saudi Exchange and Argaam in writing about licence terms. Check the market rules from two sources each (price limit, settlement, lot, trading days, Ramadan hours). Add `sa` to `model/markets.py`. Write the adapter. Run one spec on `cn_a` and on `sa`.

**5 Agent.** Done: `python3 -m model.verify` (reproduce a Result from its receipt), a 36-question eval in three languages, `POST /api/engine/ask` (question, spec, run, claims), `jsonschema` declared, `complete()` for the Anthropic API, the ask box and the explanation on `/ai`, all tested with a scripted model. To do: run the eval with a key, regenerate `uv.lock`, cache runs only if a measurement asks for it. The eval has 36 questions, 12 of them refusals and 2 with injected stop-loss or take-profit; it has not been run on a model. Proposed targets: valid specs 95%, correct 80%, refusals 100%. Add a reproduce control on `/ai`; archive snapshots by data version.

**6 Screens.** If the user chooses a rebuild: add the exclusion funnel, the gross curve, the trial count and the Sharia check detail to the Result; store saved runs; rebuild `StrategyDetail`, the Screener, compare and report on results; delete the TypeScript copies and `test_shared_facts.py`; derive the e2e route lists from `screens.ts`.

**7 Completeness.** Disclaimer review; regulatory advice for Saudi Arabia and China; coded warnings with translations; a daily refresh job and a snapshot retention rule; a runbook.

**8 Hygiene.** e2e on system Chrome in CI; the design gate in CI; move from `RefResolver` to `referencing`; confirm the `polish` "Stop" failure on system Chrome (it also fails on the first commit of `main` here); licence file and dependency audit.

## Order

1, then the fill, tradability and cost work of phase 2, then 5, then 3, then the rest of 2, then 6, then 4, then 7, then 8. Phase 5 comes early because it is the first time the product's main line (ask, rules, backtest, explanation) works from end to end. Licence enquiries for phases 3 and 4 start now, because they take longest.

## Stop points

- S1: real data in `/ai`.
- S2: the main line works end to end.
- S3: Sharia on real inputs.
- S4: phases 6 and 7 done.

## Not in scope

Orders, brokers, custody, advice, price prediction, intraday, native mobile.
