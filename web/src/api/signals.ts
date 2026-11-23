import type { GridView } from '../lib/gridcheck'
import { FAMILY_DECAY, GRID_REASONS } from '../lib/gridcheck'
import type { FactorFamily } from '../lib/gridcheck'
import { asArray, asRecord, finiteNumber, needString } from './parse'

/**
 * A run of the engine, as `model/signals.schema.json` (1.2) writes it. Field names
 * keep the wire's snake_case so a reader can lay this type next to the schema.
 *
 * The parser reads what the screen shows and refuses what breaks the contract's
 * invariants; it does not re-check that the spec is closed. The engine and the
 * validator in front of the model own that, and a second list of allowed spec
 * fields here would be a second owner.
 */

export type Sharia = 'compliant' | 'non_compliant' | 'unknown'

export type Spec = {
  market: string
  universe: string
  sharia: 'off' | 'compliant_only'
  filters: { factor: string; op: 'lt' | 'lte' | 'gt' | 'gte'; value: number }[]
  rank: { factor: string; direction: 'asc' | 'desc' }[]
  top_k: number
  n_drop: number
  rebalance: 'D' | 'W' | 'M' | 'Q' | 'A'
  period: { start: string; end: string }
  costs: { fee_rate: number; slip_rate: number }
}

export type SignalRow = {
  symbol: string
  name: string
  rank: number
  score: number
  factors: Record<string, number>
  sector?: string
  sharia?: Sharia
  weight?: number
}

export type Signals = {
  run_id: string
  as_of: string
  query: string
  spec: Spec
  receipt: { spec_hash: string; data_version: string; engine_version: string }
  rows: SignalRow[]
  metrics: { annual_return: number; max_drawdown: number; sharpe: number; turnover: number | null } | null
  curve: number[]
  grid: GridView
  warnings: string[]
}

export class SignalsError extends Error {
  constructor(what: string) {
    super(`unreadable result (${what})`)
    this.name = 'SignalsError'
  }
}

const bad = (what: string) => new SignalsError(what)

function pick<T extends string>(raw: unknown, allowed: readonly T[], what: string): T {
  if (typeof raw === 'string' && (allowed as readonly string[]).includes(raw)) return raw as T
  throw bad(what)
}

function needNumber(raw: unknown, what: string): number {
  const n = finiteNumber(raw)
  if (n === null || typeof raw !== 'number') throw bad(what)
  return n
}

const FAMILIES = Object.keys(FAMILY_DECAY) as FactorFamily[]

function parseSpec(raw: unknown): Spec {
  const r = asRecord(raw, 'spec')
  const period = asRecord(r.period, 'spec.period')
  const costs = asRecord(r.costs, 'spec.costs')
  return {
    market: needString(r.market, 'spec.market'),
    universe: needString(r.universe, 'spec.universe'),
    sharia: pick(r.sharia, ['off', 'compliant_only'], 'spec.sharia'),
    filters: asArray(r.filters, 'spec.filters').map((item, i) => {
      const f = asRecord(item, `spec.filters[${i}]`)
      return {
        factor: needString(f.factor, 'filter.factor'),
        op: pick(f.op, ['lt', 'lte', 'gt', 'gte'], 'filter.op'),
        value: needNumber(f.value, 'filter.value'),
      }
    }),
    rank: asArray(r.rank, 'spec.rank').map((item, i) => {
      const f = asRecord(item, `spec.rank[${i}]`)
      return {
        factor: needString(f.factor, 'rank.factor'),
        direction: pick(f.direction, ['asc', 'desc'], 'rank.direction'),
      }
    }),
    top_k: needNumber(r.top_k, 'spec.top_k'),
    n_drop: needNumber(r.n_drop, 'spec.n_drop'),
    rebalance: pick(r.rebalance, ['D', 'W', 'M', 'Q', 'A'], 'spec.rebalance'),
    period: { start: needString(period.start, 'period.start'), end: needString(period.end, 'period.end') },
    costs: { fee_rate: needNumber(costs.fee_rate, 'costs.fee_rate'), slip_rate: needNumber(costs.slip_rate, 'costs.slip_rate') },
  }
}

function parseRow(raw: unknown, i: number): SignalRow {
  const r = asRecord(raw, `rows[${i}]`)
  const factors: Record<string, number> = {}
  for (const [key, value] of Object.entries(asRecord(r.factors, 'row.factors'))) {
    factors[key] = needNumber(value, `row.factors.${key}`)
  }
  return {
    symbol: needString(r.symbol, 'row.symbol'),
    name: needString(r.name, 'row.name'),
    rank: needNumber(r.rank, 'row.rank'),
    score: needNumber(r.score, 'row.score'),
    factors,
    sector: typeof r.sector === 'string' ? r.sector : undefined,
    sharia: r.sharia === undefined ? undefined : pick<Sharia>(r.sharia, ['compliant', 'non_compliant', 'unknown'], 'row.sharia'),
    weight: r.weight === undefined ? undefined : needNumber(r.weight, 'row.weight'),
  }
}

function parseGrid(raw: unknown): GridView {
  const g = asRecord(asRecord(raw, 'audit').grid, 'audit.grid')
  const persistence = g.persistence === null || g.persistence === undefined ? null : asRecord(g.persistence, 'grid.persistence')
  return {
    score: needNumber(g.score, 'grid.score'),
    verdict: pick(g.verdict, ['crossSection', 'thin', 'gridlike'], 'grid.verdict'),
    families: asArray(g.families, 'grid.families').map((f) => pick(f, FAMILIES, 'grid.family')),
    findings: asArray(g.findings, 'grid.findings').map((item) => {
      const f = asRecord(item, 'grid.finding')
      return { id: pick(f.id, GRID_REASONS, 'finding.id'), points: needNumber(f.points, 'finding.points') }
    }),
    exposure:
      g.path_exposure === null || g.path_exposure === undefined
        ? null
        : { volShare: needNumber(g.path_exposure, 'grid.path_exposure') },
    persistence: persistence
      ? {
          gamma1: needNumber(persistence.gamma1, 'persistence.gamma1'),
          stop: pick(persistence.stop, ['adds', 'insurance', 'hurts'], 'persistence.stop'),
        }
      : null,
  }
}

export function parseSignals(raw: unknown): Signals {
  const r = asRecord(raw, 'signals')
  if (r.schema_version !== '1.2') throw bad(`schema_version ${String(r.schema_version)}`)
  const spec = parseSpec(r.spec)
  const rows = asArray(r.rows, 'rows').map(parseRow)
  // The Sharia screen runs before ranking: a ranked row under compliant_only is compliant.
  if (spec.sharia === 'compliant_only' && rows.some((row) => row.sharia !== 'compliant')) {
    throw bad('a ranked row is not compliant')
  }
  const receipt = asRecord(r.receipt, 'receipt')
  const backtest = r.backtest === undefined ? null : asRecord(r.backtest, 'backtest')
  const m = backtest ? asRecord(backtest.metrics, 'backtest.metrics') : null
  return {
    run_id: needString(r.run_id, 'run_id'),
    as_of: needString(r.as_of, 'as_of'),
    query: needString(r.query, 'query'),
    spec,
    receipt: {
      spec_hash: needString(receipt.spec_hash, 'receipt.spec_hash'),
      data_version: needString(receipt.data_version, 'receipt.data_version'),
      engine_version: needString(receipt.engine_version, 'receipt.engine_version'),
    },
    rows,
    metrics: m
      ? {
          annual_return: needNumber(m.annual_return, 'metrics.annual_return'),
          max_drawdown: needNumber(m.max_drawdown, 'metrics.max_drawdown'),
          sharpe: needNumber(m.sharpe, 'metrics.sharpe'),
          turnover: m.turnover === undefined ? null : needNumber(m.turnover, 'metrics.turnover'),
        }
      : null,
    curve:
      backtest && backtest.equity_curve !== undefined
        ? asArray(backtest.equity_curve, 'equity_curve').map((p) => needNumber(asRecord(p, 'point').value, 'point.value'))
        : [],
    grid: parseGrid(r.audit),
    warnings: Array.isArray(r.warnings) ? r.warnings.filter((w): w is string => typeof w === 'string') : [],
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

/** The latest run, or null when the engine has not written one yet. */
export async function fetchSignals(signal?: AbortSignal): Promise<Signals | null> {
  const response = await fetch(`${BASE}/api/engine/signals`, { signal })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`engine ${response.status}`)
  return parseSignals(await response.json())
}
