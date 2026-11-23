import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseSignals, SignalsError } from './signals'

/** The contract's own example, read from model/: the parser and the schema share one file. */
const EXAMPLE: Record<string, any> = JSON.parse(
  // vitest runs from web/, so the contract sits one level up.
  readFileSync(resolve(process.cwd(), '../model/signals.example.json'), 'utf8'),
)
const clone = () => structuredClone(EXAMPLE)

describe('parseSignals', () => {
  it('reads the contract example', () => {
    const s = parseSignals(EXAMPLE)
    expect(s.spec.rank.map((r) => r.factor)).toEqual(['debt_ratio', 'dividend_yield'])
    expect(s.rows).toHaveLength(2)
    expect(s.grid.verdict).toBe('crossSection')
    expect(s.grid.persistence).toEqual({ gamma1: 0.34, stop: 'adds' })
    expect(s.metrics?.sharpe).toBeCloseTo(0.91)
  })

  it('treats a missing backtest as no metrics and no curve, not as zero', () => {
    const doc = clone()
    delete doc.backtest
    const s = parseSignals(doc)
    expect(s.metrics).toBeNull()
    expect(s.curve).toEqual([])
  })

  it('keeps a null path exposure and a null persistence as unknown', () => {
    const doc = clone()
    doc.audit.grid.path_exposure = null
    doc.audit.grid.persistence = null
    const s = parseSignals(doc)
    expect(s.grid.exposure).toBeNull()
    expect(s.grid.persistence).toBeNull()
  })

  const refuses: [string, (d: Record<string, any>) => void][] = [
    ['another schema version', (d) => (d.schema_version = '1.1')],
    ['a result with no audit', (d) => delete d.audit],
    ['a grid finding with no points', (d) => (d.audit.grid.findings = [{ id: 'priceOnly' }])],
    ['a persistence with no stop verdict', (d) => (d.audit.grid.persistence = { gamma1: 0.1, sr: 0.1 })],
    ['an unknown verdict', (d) => (d.audit.grid.verdict = 'great')],
    ['a number that is a string', (d) => (d.backtest.metrics.sharpe = '0.91')],
    ['a non-finite number', (d) => (d.backtest.metrics.sharpe = null)],
    ['a spec with no n_drop', (d) => delete d.spec.n_drop],
    ['an unknown rebalance', (d) => (d.spec.rebalance = 'X')],
    ['a row with no factors', (d) => delete d.rows[0].factors],
    ['an unreadable body', (d) => (d.rows = 'none')],
  ]
  for (const [name, mutate] of refuses) {
    it(`refuses ${name}`, () => {
      const doc = clone()
      mutate(doc)
      expect(() => parseSignals(doc)).toThrow()
    })
  }

  it('refuses a non-compliant or unproven row under compliant_only, as the schema does', () => {
    for (const state of ['unknown', 'non_compliant', undefined]) {
      const doc = clone()
      doc.spec.sharia = 'compliant_only'
      doc.rows.forEach((r: Record<string, unknown>) => (r.sharia = 'compliant'))
      doc.rows[0].sharia = state
      expect(() => parseSignals(doc)).toThrow(SignalsError)
    }
  })

  it('accepts compliant_only when every ranked row is compliant', () => {
    const doc = clone()
    doc.spec.sharia = 'compliant_only'
    doc.rows.forEach((r: Record<string, unknown>) => (r.sharia = 'compliant'))
    expect(parseSignals(doc).rows.every((r) => r.sharia === 'compliant')).toBe(true)
  })
})
