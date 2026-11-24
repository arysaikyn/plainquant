import type { Lang } from '../../i18n'
import { fmtNum, fmtPct } from '../../i18n'
import { isolate } from '../../i18n/format'
import type { Scalar } from '../../api/ask'

/**
 * A claim's value is the engine's; only its look is chosen here, from the name of the field
 * it points at. A fraction that means a return or a share is shown as a percent; any other
 * whole number as an integer (a count, a rank, a score); any other number with two decimals.
 * A word (a verdict, a date, a symbol) is shown as it is.
 */
const RETURNS = /(annual_return|max_drawdown)$/
const SHARES = /(turnover|path_exposure|weight|fee_rate|slip_rate)$/

export function claimValue(ref: string, value: Scalar, lang: Lang): string {
  if (typeof value === 'number') {
    if (RETURNS.test(ref)) return fmtPct(value, lang, 1)
    if (SHARES.test(ref)) return fmtNum(value * 100, lang, 1, '%')
    if (Number.isInteger(value)) return fmtNum(value, lang, 0)
    return fmtNum(value, lang, 2)
  }
  if (value === null) return '–'
  return isolate(String(value))
}
