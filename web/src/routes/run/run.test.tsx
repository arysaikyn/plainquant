import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n'
import { parseSignals, SignalsError } from '../../api/signals'

const fetchSignals = vi.hoisted(() => vi.fn())
vi.mock('../../api/signals', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/signals')>()),
  fetchSignals,
}))

import RunPage from './index'

const EXAMPLE = parseSignals(
  JSON.parse(readFileSync(resolve(process.cwd(), '../model/signals.example.json'), 'utf8')),
)

function show() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <RunPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

/** Numbers are wrapped in bidi isolates for Arabic; the words around them are what we read. */
const plain = (el: Element) => (el.textContent ?? '').replace(/[\u2066\u2069]/g, '')

describe('engine run screen', () => {
  beforeEach(() => {
    localStorage.setItem('app.lang', 'en')
    fetchSignals.mockReset()
  })

  it('shows the grid check before the result, as the product rule says', async () => {
    fetchSignals.mockResolvedValue(EXAMPLE)
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    const grid = container.querySelector('#grid-check')
    const result = container.querySelector('#run-result')
    expect(grid).not.toBeNull()
    expect(result).not.toBeNull()
    expect(grid!.compareDocumentPosition(result!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('says the rules in words, with factor names and the engine receipt', async () => {
    fetchSignals.mockResolvedValue(EXAMPLE)
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    expect(plain(container)).toContain('Rank by Debt ratio (lower first) · Dividend yield (higher first)')
    expect(plain(container)).toContain('Hold 2 names; replace at most 0 at each rebalance; rebalance monthly')
    expect(container.textContent).toContain(EXAMPLE.receipt.spec_hash.slice(0, 16))
    expect(container.textContent).toContain(EXAMPLE.receipt.data_version)
  })

  it('shows an unknown factor id as itself, never as nothing', async () => {
    fetchSignals.mockResolvedValue({
      ...EXAMPLE,
      spec: { ...EXAMPLE.spec, rank: [{ factor: 'vibes', direction: 'desc' as const }] },
    })
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    expect(plain(container)).toContain('Rank by vibes (higher first)')
  })

  it('leaves out the metrics section when the run had no backtest, instead of printing zeros', async () => {
    fetchSignals.mockResolvedValue({ ...EXAMPLE, metrics: null, curve: [] })
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    expect(container.querySelector('#run-result')).toBeNull()
  })

  it('tells the reader how to make a run when there is none', async () => {
    fetchSignals.mockResolvedValue(null)
    const { container } = show()
    await screen.findByText('No run yet.')
    expect(container.textContent).toContain('python3 -m model')
  })

  it('offers a retry when the result cannot be read, and retries', async () => {
    fetchSignals.mockRejectedValueOnce(new SignalsError('rows')).mockResolvedValueOnce(EXAMPLE)
    show()
    const retry = await screen.findByRole('button', { name: /retry/i })
    retry.click()
    await waitFor(() => expect(screen.getByText(EXAMPLE.query)).toBeTruthy())
    expect(fetchSignals).toHaveBeenCalledTimes(2)
  })
})
