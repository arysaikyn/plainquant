import { Fragment, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GridCheck } from '../../components/GridCheck'
import { Screen } from '../../components/Screen'
import { EmptyState, ErrorState, Skeleton } from '../../components/states'
import { fmtNum, fmtPct, useI18n, useStrings } from '../../i18n'
import { fill, isolate } from '../../i18n/format'
import { fetchSignals } from '../../api/signals'
import type { Sharia, Signals } from '../../api/signals'
import { Sparkline } from '../ai/Sparkline'
import type { Segment } from '../../api/ask'
import { AskBox } from './AskBox'
import type { RunOutcome } from './AskBox'
import { claimValue } from './claims'
import { strings } from './strings'
import type { RunStrings } from './strings'

type Claims = { segments: Segment[][]; dropped: number; error?: string }
type State = { kind: 'loading' } | { kind: 'empty' } | { kind: 'error' } | { kind: 'ready'; run: Signals }

const OP = { lt: '<', lte: '≤', gt: '>', gte: '≥' } as const
const COMMAND = 'python3 -m model SPEC.json SNAPSHOT_DIR --query "…" -o model/signals.json'

/**
 * One run of the engine, as the engine wrote it. The screen formats and orders; it
 * computes nothing. The grid check comes before the result, as the product rule says.
 */
export default function RunPage() {
  const s = useStrings<RunStrings>(strings)
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [tick, setTick] = useState(0)
  const [claims, setClaims] = useState<Claims | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchSignals(controller.signal)
      .then((run) => setState(run ? { kind: 'ready', run } : { kind: 'empty' }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [tick])

  return (
    <Screen title={s('title')}>
      <div className="pt-4">
        <p className="text-md leading-relaxed text-muted">{s('lead')}</p>

        <AskBox
          onRun={(outcome: RunOutcome) => {
            setState({ kind: 'ready', run: outcome.run })
            setClaims({ segments: outcome.claims, dropped: outcome.dropped, error: outcome.claimsError })
          }}
        />

        {state.kind === 'loading' && (
          <div className="mt-5" aria-busy="true" aria-label={s('loading')}>
            <Skeleton rows={4} />
          </div>
        )}

        {state.kind === 'empty' && (
          <div className="mt-5">
            <EmptyState text={s('empty')} />
            <p className="mt-2 text-sm text-muted">{s('emptyHow')}</p>
            <pre dir="ltr" className="panel mt-2 overflow-x-auto p-3 text-xs">
              <code>{COMMAND}</code>
            </pre>
          </div>
        )}

        {state.kind === 'error' && (
          <div className="mt-5">
            <ErrorState
              message={s('error')}
              onRetry={() => {
                setState({ kind: 'loading' })
                setTick((n) => n + 1)
              }}
            />
          </div>
        )}

        {state.kind === 'ready' && <Ready run={state.run} claims={claims} />}

        <Link
          to="/ai/chat"
          className="mt-8 block border-t border-line py-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg"
        >
          <span className="text-sm underline decoration-line underline-offset-4">{s('assistant')}</span>
          <span className="mt-1 block text-xs text-muted">{s('assistantNote')}</span>
        </Link>
      </div>
    </Screen>
  )

}


function Ready({ run, claims }: { run: Signals; claims: Claims | null }) {
  const { lang } = useI18n()
  const s = useStrings<RunStrings>(strings)
  const factorLabel = (id: string) => (strings[lang] as Record<string, string>)[`factor_${id}`] ?? id
  const shariaLabel: Record<Sharia, string> = {
    compliant: s('shariaCompliant'),
    non_compliant: s('shariaNon'),
    unknown: s('shariaUnknown'),
  }
  const { spec, metrics } = run
  const list = (items: string[]) => items.join(' · ')
  const first = run.curve[0]
  const last = run.curve[run.curve.length - 1]
  return (
    <>
      <section className="mt-6" aria-labelledby="run-question">
        <h2 id="run-question" className="text-sm text-muted">
          {s('question')}
        </h2>
        <p className="mt-1 text-md leading-snug">{run.query}</p>
        <p className="mt-1 text-xs text-muted">{fill(s('asOf'), { date: isolate(run.as_of) })}</p>
      </section>

      {run.warnings.length > 0 && (
        <section className="panel mt-4 p-3" aria-labelledby="run-notes">
          <h2 id="run-notes" className="text-sm">
            {s('notes')}
          </h2>
          <ul className="mt-1 text-xs text-muted">
            {run.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-6">
        <GridCheck report={run.grid} />
      </div>

      {claims && (claims.segments.length > 0 || claims.error) && (
        <section className="mt-6 border-t border-line pt-5" aria-labelledby="run-explain">
          <h2 id="run-explain" className="text-md">
            {s('explanation')}
          </h2>
          {claims.segments.length > 0 && (
            <>
              <p className="mt-1 text-xs text-muted">{s('explanationNote')}</p>
              <ul className="mt-2 space-y-2 text-sm leading-snug">
                {claims.segments.map((parts, i) => (
                  <li key={i}>
                    {parts.map((part, j) => (
                      <Fragment key={j}>
                        {'text' in part ? part.text : <span className="tabular-nums">{claimValue(part.ref, part.value, lang)}</span>}
                      </Fragment>
                    ))}
                  </li>
                ))}
              </ul>
            </>
          )}
          {claims.dropped > 0 && (
            <p className="mt-2 text-xs text-muted">{fill(s('claimsDropped'), { n: fmtNum(claims.dropped, lang, 0) })}</p>
          )}
          {claims.error && <p className="mt-2 text-xs text-muted">{s('claimsError')}</p>}
        </section>
      )}

      <section className="mt-6 border-t border-line pt-5" aria-labelledby="run-rules">
        <h2 id="run-rules" className="text-md">
          {s('rules')}
        </h2>
        <ul className="mt-2 space-y-2 text-sm leading-snug">
          {spec.sharia === 'compliant_only' && <li>{s('ruleSharia')}</li>}
          {spec.filters.length > 0 && (
            <li>
              {fill(s('ruleFilter'), {
                list: list(
                  spec.filters.map((f) => `${factorLabel(f.factor)} ${OP[f.op]} ${isolate(String(f.value))}`),
                ),
              })}
            </li>
          )}
          <li>
            {fill(s('ruleRank'), {
              list: list(spec.rank.map((r) => `${factorLabel(r.factor)} (${s(r.direction)})`)),
            })}
          </li>
          <li>
            {fill(s('ruleHold'), {
              k: fmtNum(spec.top_k, lang, 0),
              n: fmtNum(spec.n_drop, lang, 0),
              freq: s(`freq_${spec.rebalance}` as const),
            })}
          </li>
          <li>{fill(s('rulePeriod'), { start: isolate(spec.period.start), end: isolate(spec.period.end) })}</li>
          <li>
            {fill(s('ruleCosts'), {
              fee: fmtNum(spec.costs.fee_rate * 100, lang, 2, '%'),
              slip: fmtNum(spec.costs.slip_rate * 100, lang, 2, '%'),
            })}
          </li>
        </ul>
      </section>

      {metrics && (
        <section className="mt-6 border-t border-line pt-5" aria-labelledby="run-result">
          <h2 id="run-result" className="text-md">
            {s('result')}
          </h2>
          <dl className="mt-3 grid grid-cols-2 gap-3">
            {(
              [
                [s('annual'), fmtPct(metrics.annual_return, lang, 1)],
                [s('drawdown'), fmtPct(metrics.max_drawdown, lang, 1)],
                [s('sharpe'), fmtNum(metrics.sharpe, lang, 2)],
                ...(metrics.turnover === null ? [] : [[s('turnover'), fmtNum(metrics.turnover * 100, lang, 0, '%')]]),
              ] as [string, string][]
            ).map(([label, value]) => (
              <div key={label} className="panel p-3">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-1 text-lg tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          {run.curve.length > 1 && (
            <figure className="mt-4">
              <div className="[&_svg]:h-auto [&_svg]:w-full" style={{ color: 'var(--color-accent)' }}>
                <Sparkline data={run.curve} w={300} h={64} />
              </div>
              <figcaption className="mt-1 text-xs text-muted">
                {s('curve')} ·{' '}
                {fill(s('curveRange'), { from: fmtNum(first, lang, 2), to: fmtNum(last, lang, 2) })}
              </figcaption>
            </figure>
          )}
        </section>
      )}

      <section className="mt-6 border-t border-line pt-5" aria-labelledby="run-holdings">
        <h2 id="run-holdings" className="text-md">
          {s('holdings')}
        </h2>
        <ul className="mt-2 divide-y divide-line">
          {run.rows.map((row) => (
            <li key={row.symbol} className="flex min-h-11 items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <div className="text-sm leading-tight">
                  <span className="tabular-nums text-muted">{fmtNum(row.rank, lang, 0)}</span> {row.name}
                </div>
                <div className="text-xs text-muted">{isolate(row.symbol)}</div>
              </div>
              <div className="shrink-0 text-end text-xs">
                {row.weight !== undefined && (
                  <div className="tabular-nums">
                    {s('weight')} {fmtNum(row.weight * 100, lang, 1, '%')}
                  </div>
                )}
                {row.sharia && <div className="text-muted">{shariaLabel[row.sharia]}</div>}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6 border-t border-line pt-5" aria-labelledby="run-receipt">
        <h2 id="run-receipt" className="text-md">
          {s('receipt')}
        </h2>
        <p className="mt-1 text-xs text-muted">{s('receiptLead')}</p>
        <dl className="mt-3 space-y-2 text-xs">
          {(
            [
              [s('specHash'), run.receipt.spec_hash.slice(0, 16)],
              [s('dataVersion'), run.receipt.data_version],
              [s('engine'), run.receipt.engine_version],
            ] as [string, string][]
          ).map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-3">
              <dt className="text-muted">{label}</dt>
              <dd dir="ltr" className="min-w-0 break-all text-end tabular-nums">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  )
}
