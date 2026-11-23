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
  seeded fixture. No real data source is chosen: the candidates (AKShare, Tushare) have
  unverified terms and no verified announcement dates, so a vendor adapter waits for that.
  `web/` still reads mock data.
- `web/src/lib/ledger.ts`, `lib/gridcheck.ts` and `data/shariaCoverage.ts` hold a second
  copy of what `model/audit.py` and `model/sharia.py` now compute. They go from `web/`
  when it reads a Result. `audit.py` was checked against the compiled `gridcheck.ts` on
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
  top 10) and the three refusal names, which `web/src/data/costs.ts` and `lib/refusal.ts`
  also hold. Delete the web copies when web reads a Result.
- Factor ids are free strings in `spec.schema.json`; the closed vocabulary is the registry
  in `model/factors.py`. A spec that names an unregistered factor passes the schema and is
  refused by the engine. Listing the ids in the schema would make that one check, not two,
  but it would also make the schema a second owner of the factor list.
- The kernel is pure Python over CSV. That is fine for an index-sized universe (hundreds of
  names, six years of daily closes); a full A-share snapshot is millions of rows and will
  need a columnar reader. Add that dependency when a measurement says so, not before.
- `model/store.py` imports `canonical()` from `model/run.py`, a loader depending on the
  runner. It is the one hashing function; move it only if a third caller appears.
- Market differences (T+1, price limits, lot size, calendar, costs) need a per-market
  adapter in the engine. `costs` in the spec carries only the rates.
- The Saudi data source is unverified (`product.md`, open question 1). The `sa` market is
  in the enum and nothing more.

## Wiring the web app: the gap, field by field

The strategy screen was built on a mock `Strategy`, not on a Result, so reading a Result
there is a redesign and not a swap. What it needs against what a Result carries:

| The screen needs | In a Result? | Call |
|---|---|---|
| Net equity curve, return, drawdown, Sharpe, turnover | yes (`backtest`) | use it |
| Ranked names, scores, weights, Sharia state | yes (`rows`) | use it |
| Receipt: spec, data version, engine version | yes (`spec`, `receipt`) | replaces the FNV receipt |
| Grid score, verdict, families, findings, exposure, persistence | yes (`audit.grid`) | use it |
| Grid `stop` verdict and `sr` | no: only `gamma1` | add one enum to `audit.grid`, or drop the line |
| Gross curve and cost row | no | derive from `spec.costs` and `turnover`, or drop |
| Localized rule labels and descriptions | no, by design | web owns labels keyed by factor id |
| Deflated Sharpe | no: needs a trial count the engine has no concept of | keep labelled demo, or delete; do not invent trials |
| Drop ledger (why each name was excluded) | no: holdings only | add a funnel to the Result only when a screen needs it |
| Cross-market lens | no: one market per run | out until a second market has real data |

Recommendation: do not retrofit `StrategyDetail`. Add one screen that renders a Result as
it is (question, the spec as a sentence, receipt, metrics, curve, rows, grid), as one row
in `screens.ts` plus its translations, and let the mock screens keep their demo label.
Then move the screener's live grid check behind the backend (`app.py` gains an allowlisted
engine path) and delete the TS copies. That is a UI design decision and a contract
addition (`stop`), so it waits for you.

## Running it

    python3 -m model SPEC.json SNAPSHOT_DIR --query "..." -o model/signals.json

`model/signals.json` is generated and gitignored. Tests: `python3 -m unittest discover -s
model/tests -t .`; the contract tests need `jsonschema` and are skipped without it.
