import { describe, expect, it } from 'vitest'
import { claimValue } from './claims'

/** Numbers are wrapped in bidi isolates; the digits and signs are what we read. */
const plain = (s: string) => s.replace(/[⁦⁩]/g, '')

describe('claimValue', () => {
  it('shows a return and a drawdown as a signed percent', () => {
    expect(plain(claimValue('backtest.metrics.annual_return', 0.128, 'en'))).toBe('+12.8%')
    expect(plain(claimValue('backtest.metrics.max_drawdown', -0.184, 'en'))).toBe('-18.4%')
  })

  it('shows a share as a percent without a sign', () => {
    expect(plain(claimValue('rows.0.weight', 0.5, 'en'))).toBe('50.0%')
    expect(plain(claimValue('backtest.metrics.turnover', 0.35, 'en'))).toBe('35.0%')
    expect(plain(claimValue('spec.costs.fee_rate', 0.0015, 'en'))).toBe('0.2%')
  })

  it('shows a whole number as an integer and any other number with two decimals', () => {
    expect(plain(claimValue('spec.top_k', 10, 'en'))).toBe('10')
    expect(plain(claimValue('audit.grid.score', 0, 'en'))).toBe('0')
    expect(plain(claimValue('backtest.metrics.sharpe', 0.91, 'en'))).toBe('0.91')
    expect(plain(claimValue('rows.0.score', 1.8234, 'en'))).toBe('1.82')
  })

  it('uses Latin digits in every language', () => {
    expect(plain(claimValue('backtest.metrics.sharpe', 0.91, 'ar'))).toBe('0.91')
    expect(plain(claimValue('spec.top_k', 10, 'zh'))).toBe('10')
  })

  it('shows words as they are, isolated, and a missing value as a dash', () => {
    expect(plain(claimValue('audit.grid.verdict', 'crossSection', 'en'))).toBe('crossSection')
    expect(plain(claimValue('rows.0.symbol', '600036.SH', 'ar'))).toBe('600036.SH')
    expect(claimValue('audit.grid.persistence', null, 'en')).toBe('–')
  })
})
