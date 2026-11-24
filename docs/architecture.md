# Architecture

Where the trust boundary sits, and what crosses it. Product scope is in
`product.md`; the contract text is in `model/`.

## The spine

```
question --LLM--> Spec --engine + data snapshot--> Result --LLM--> claims --> web
                   |                                 |
        model/spec.schema.json            model/signals.schema.json
```

- **Spec** is what the user asked for, as explicit rules. The model writes it. It is a
  closed object: no stop-loss, take-profit or entry-price field exists, and `n_drop` is
  required, so a spec always says how a holding ends — by leaving the ranking.
- **Engine** is a pure function of a spec and a point-in-time data snapshot. It is the
  only place a number is computed. It also runs the Sharia filter before ranking and the
  grid check, so a result cannot be emitted without its audit.
- **Result** (`signals.json`) embeds the spec it ran and a receipt: spec hash, data
  version, engine version. Same three, same result.
- **Web** renders the result. It formats; it does not compute.

## Fill timing

A rebalance ranks on the close of the rebalance day and fills on the close of the next
trading day. Ranking and filling on one close would trade at a price the strategy had
already seen. At the end of the data, where there is no next day, the last day stands in.
The equity curve's dates are fill dates; `as_of` is the last ranking day. Tests: the fill
date and the period return are computed from the fill prices, data after the last fill
cannot change a result, and prices after a ranking day cannot change the ranking.

## Where each invariant is enforced

| Invariant | Enforced by | Not by |
|---|---|---|
| No price-level exits | the spec has no such field (`additionalProperties: false`) | a UI check |
| A spec states its exit | `n_drop` is required | the `noExitPolicy` finding |
| Sharia before rank; unknown is not compliant | the engine, and the result schema rejects a non-compliant row under `compliant_only` | `lib/ledger.ts` |
| Grid verdict before the result | `audit.grid` is required | a UI convention |
| One fact, one owner | market, rebalance, period and sharia live in the spec only | repeating them in the result |

## What the model may do

It may write a spec and explain a result. It may not write a number the result does not
contain. Both are enforced in `agent/`, with the model behind one function,
`complete(messages) -> str`:

- `agent/spec.py` extracts the model's JSON, validates it against `spec.schema.json`, the
  factor registry and the available universes, and gives the model two repairs. It fails
  rather than guesses. A question that asks for an order, a guarantee or a pick is
  answered `{"refuse": rule}`, the three rules of `lib/refusal.ts`.
- `agent/claims.py` takes sentences with slots (`{backtest.metrics.sharpe}`). The value
  comes from the Result; a sentence with a digit of its own, or a slot that names nothing,
  is dropped. The renderer gets segments and formats them with the web's number formatter.
  `routes/ai/numerals.ts`, which scans a finished answer, stays for Vibe-Trading's free
  text, the one path that cannot use claims.
- `agent/evaluate.py` and `agent/evals/spec_cases.json` score a model on eight questions:
  how many become a valid spec, how many say what was asked, how many refusals are right.

Vibe-Trading sits outside this boundary. It runs model-written Python, so its numbers are
untraced and the UI already marks them so. It is a research assistant, not the engine.

## Not done yet

- **The engine runs on synthetic data only.** `model/` writes a valid Result from a
  seeded fixture. `data/baostock_source.py` can fill a snapshot with real A-share data, but
  it has only run against a fake service: it has not been run on live data, and the field
  names it reads are from Baostock's documentation, not checked against a response (see
  "Real data" below).
  Only `/run` in `web/` reads a Result.
- `web/src/lib/ledger.ts`, `lib/gridcheck.ts` and `data/shariaCoverage.ts` hold a second
  copy of what `model/audit.py` and `model/sharia.py` now compute. They go from `web/`
  when the strategy screen and the screener stop using them. `audit.py` was checked against the compiled `gridcheck.ts` on
  the same inputs (2026-11-23, Node 22.23.5): noise, regression coefficients, `gamma1`,
  `sr` and the full report agree to the last digit. That check is a one-off, not in CI.
  `sharia.py` is a logic port (same precedence and caps), not a numeric comparison: the
  TS side reads mock fundamentals.
- The grid check is uncalibrated. Its points are hand-set, and on pure-noise synthetic
  data a fundamental spec still collects `volHarvest` from a 71-period regression. Treat
  the score as a prompt to look, not a measurement, until it is tuned against known cases.
- **No model has been run against `agent/`.** The boundary is tested with scripted replies;
  whether a real model writes valid specs from the prompt is unmeasured, and that is what
  the eval is for. `agent/` needs `jsonschema` at runtime; it is declared nowhere yet and
  belongs in `backend/pyproject.toml` when the backend imports it. Nothing in `backend/` or
  `web/` calls `agent/` yet.
- `agent/spec.py` holds the defaults for a silent question (fee 0.0015, slippage 0.005,
  top 10) and the three refusal names. `web/src` holds a second copy of the fee and
  slippage, of the refusal names and of the AAOIFI caps. `model/tests/test_shared_facts.py`
  reads those TypeScript files and fails the engine job when a value differs. The copies go
  when the screens that use them are rebuilt on engine results.
- Factor ids are free strings in `spec.schema.json`; the closed vocabulary is the registry
  in `model/factors.py`. A spec that names an unregistered factor passes the schema and is
  refused by the engine. Listing the ids in the schema would make that one check, not two,
  but it would also make the schema a second owner of the factor list.
- The kernel is pure Python over CSV. Measured on 2026-11-23 on synthetic data, 300 names
  and 6 years of daily closes (469 800 prices): a monthly run takes 0.28 s, a weekly run
  1.1 s, reading the snapshot 1.7 s, peak memory 181 MB. A full A-share snapshot is about
  17 times larger; that is an extrapolation, not a measurement, and it would not fit in the
  1 GB of the development machine. Add a columnar reader when a measurement says so.
- `model/store.py` imports `canonical()` from `model/run.py`, a loader depending on the
  runner. It is the one hashing function; move it only if a third caller appears.
- Market rules are one table, `model/markets.py`. It registers `cn_a` only, with the three
  frictions the engine does not model: T+1 settlement, daily price limits and 100-share
  board lots (Shanghai Stock Exchange rule pages, checked 2026-11-23). The limits differ by
  board and the sources disagree on some boards, so no percentage is written. A Snapshot
  carries its market; the engine refuses a spec whose market differs from the snapshot's,
  and refuses a market with no entry. Every Result starts its `warnings` with the list of
  what is not modelled. `sa`, `hk` and `us` stay in the schema enum and are refused until
  someone writes their frictions and holds data for them.
- The warning text is English whatever the app language. A coded warning would fix that and
  would change the contract; it waits for a second warning that the UI must translate.
- No Saudi data source is cleared (`product.md`, open question 1), so nothing runs for `sa`.

## Real data

`data/baostock_source.py` builds a snapshot from Baostock, a free A-share service, into
`data/raw/` (git ignores it). The module is stdlib plus the `baostock` package, which is
not a dependency of this repo. Run it with a package you have read:

    PYTHONPATH=<dir holding baostock> python3 -m data.baostock_source --out data/raw/csi300 --limit 20
    python3 -m model SPEC.json data/raw/csi300 --query "..." -o model/signals.json

What it does about point in time: a report becomes visible on its publication date, not its
period end; each fact row repeats every value known that day, because the engine reads the
latest row only. A mutation test (publish on the period end) makes the suite fail.

What it cannot fix is written into the snapshot as `limitations`, and every Result run on it
starts its `warnings` with them: the universe is today's CSI 300 list (survivorship bias);
`debt_ratio` is liabilities over assets, not the AAOIFI ratio; the AAOIFI inputs are not
published, so every name is Sharia unknown and `compliant_only` returns nothing; the
dividend yield only changes on an announcement.

Not confirmed: that Baostock's field names match the code, and whether its data may be
shown or redistributed. A missing field stops the run and lists the fields the server sent.

## Wiring the web app

`/run` renders a Result as it is: the question, the grid check first, the rules as
sentences, metrics, curve, holdings and the receipt. It is one row in `screens.ts` plus
`routes/run/`, reached from the strategy list. The data path is `GET /api/engine/signals`
(`backend/app.py` serves the latest `model/signals.json`, read-only, one fixed path) into a
strict parser, `web/src/api/signals.ts`, whose tests read `model/signals.example.json`, so
the parser and the schema share one example.

Gaps between the strategy screen and a Result, and how each was settled:

| The screen wanted | In a Result? | Settled |
|---|---|---|
| Grid finding points, persistence `sr` and `stop` | no | added to the contract: `findings` is `{id, points}`, `persistence` is `{gamma1, stop}`; without them a Result explained its score less than the engine had |
| Gross curve and cost row | no | not shown; the costs appear as a rule |
| Localized rule labels | no, by design | web owns them, keyed by factor id (`routes/run/strings.ts`); an id with no label is shown as itself |
| Deflated Sharpe | no: needs a trial count | not shown; it stays on the labelled demo screens |
| Drop ledger, cross-market lens | no | not shown |

Still on mock data: Markets, News, the strategy list and detail, the Screener, the AI demo.
The TS copies of the grid check, the ledger and the Sharia caps remain because
`StrategyDetail` and the Screener still compute with them. They go when those screens do.

## Running it

    python3 -m model SPEC.json SNAPSHOT_DIR --query "..." -o model/signals.json

`model/signals.json` is generated and gitignored. Tests: `python3 -m unittest discover -s
model/tests -t .`; the contract tests need `jsonschema` and are skipped without it.
