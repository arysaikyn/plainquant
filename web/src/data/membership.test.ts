import { describe, expect, it } from 'vitest'
import { sectors } from './mock'
import { membersChange, membersOf } from './membership'

describe('members by currency', () => {
  it('lists only names priced in the asked currency', () => {
    for (const sec of sectors) {
      for (const currency of ['SAR', 'CNY', 'HKD']) {
        for (const q of membersOf(sec.id, currency)) expect(q.currency).toBe(currency)
      }
    }
  })

  it('splits the unfiltered list without loss', () => {
    for (const sec of sectors) {
      const parts = ['SAR', 'CNY', 'HKD'].flatMap((c) => membersOf(sec.id, c))
      expect(parts.length).toBe(membersOf(sec.id).length)
    }
  })

  it('has no China A names in the Saudi change', () => {
    const withSaudi = sectors.find((sec) => membersOf(sec.id, 'SAR').length > 0 && membersOf(sec.id, 'CNY').length > 0)
    if (withSaudi) expect(membersChange(withSaudi.id, '1d', 'SAR')).not.toBe(membersChange(withSaudi.id, '1d'))
  })
})
