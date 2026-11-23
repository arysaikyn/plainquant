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
contain. Today `routes/ai/numerals.ts` checks this after the fact by scanning the answer;
that is a lint. The structural form is for the model to emit claims that reference result
fields (`metrics.sharpe`) and for the renderer to fill in the value.

Vibe-Trading sits outside this boundary. It runs model-written Python, so its numbers are
untraced and the UI already marks them so. It is a research assistant, not the engine.

## Not done yet

- **The engine runs on synthetic data only.** `model/` writes a valid Result from a
  seeded fixture. No real data source is chosen: the candidates (AKShare, Tushare) have
  unverified terms and no verified announcement dates, so a vendor adapter waits for that.
  `web/` still reads mock data.
- `web/src/lib/ledger.ts`, `lib/gridcheck.ts` and `data/shariaCoverage.ts` hold a second
  copy of what `model/audit.py` and `model/sharia.py` now compute. They go from `web/`
  when it reads a Result; until then the TS tests and `model/tests/test_audit.py` pin the
  same assertions, not bit-identical numbers (no Node here to compare them).
- The grid check is uncalibrated. Its points are hand-set, and on pure-noise synthetic
  data a fundamental spec still collects `volHarvest` from a 71-period regression. Treat
  the score as a prompt to look, not a measurement, until it is tuned against known cases.
- Factor ids (`debt_ratio`, `low_leverage`) are free strings. The factor library is the
  next contract.
- Market differences (T+1, price limits, lot size, calendar, costs) need a per-market
  adapter in the engine. `costs` in the spec carries only the rates.
- The Saudi data source is unverified (`product.md`, open question 1). The `sa` market is
  in the enum and nothing more.
