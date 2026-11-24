import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n'
import { parseSignals } from '../../api/signals'

const askEngine = vi.hoisted(() => vi.fn())
const fetchSignals = vi.hoisted(() => vi.fn())
vi.mock('../../api/ask', async (original) => ({ ...(await original<typeof import('../../api/ask')>()), askEngine }))
vi.mock('../../api/signals', async (original) => ({ ...(await original<typeof import('../../api/signals')>()), fetchSignals }))

import RunPage from './index'

const raw = JSON.parse(readFileSync(resolve(process.cwd(), '../model/signals.example.json'), 'utf8'))
const EXAMPLE = parseSignals(raw)
const NEW_RUN = parseSignals({ ...raw, query: 'A question typed in the box' })
const plain = (el: Element) => (el.textContent ?? '').replace(/[⁦⁩]/g, '')

function show() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <RunPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}
const box = () => screen.getByLabelText('Ask in your own words') as HTMLInputElement
const send = (text: string) => {
  fireEvent.change(box(), { target: { value: text } })
  fireEvent.submit(box().closest('form')!)
}

describe('the ask box on the run screen', () => {
  beforeEach(() => {
    localStorage.setItem('app.lang', 'en')
    askEngine.mockReset()
    fetchSignals.mockReset().mockResolvedValue(EXAMPLE)
  })

  it('fills the box from an example question and does not send it by itself', async () => {
    show()
    await screen.findByText(EXAMPLE.query)
    fireEvent.click(screen.getByRole('button', { name: 'Top 10 by six-month momentum' }))
    expect(box().value).toBe('Top 10 by six-month momentum')
    expect(askEngine).not.toHaveBeenCalled()
  })

  it('keeps the data limits closed behind one line that counts them', async () => {
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    const notes = container.querySelector('details')!
    expect(notes.open).toBe(false)
    expect(plain(notes.querySelector('summary')!)).toBe(`${EXAMPLE.warnings.length} limits on the data. Tap to read.`)
  })

  it('cannot send an empty or blank question', async () => {
    show()
    await screen.findByText(EXAMPLE.query)
    const button = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.change(box(), { target: { value: '   ' } })
    expect(button.disabled).toBe(true)
    fireEvent.change(box(), { target: { value: 'cheap' } })
    expect(button.disabled).toBe(false)
  })

  it('sends the trimmed question once and shows that it is working', async () => {
    let finish: (value: unknown) => void = () => {}
    askEngine.mockReturnValue(new Promise((resolveIt) => (finish = resolveIt)))
    show()
    await screen.findByText(EXAMPLE.query)
    send('  low debt  ')
    expect(askEngine).toHaveBeenCalledTimes(1)
    expect(askEngine.mock.calls[0][0]).toBe('low debt')
    expect(await screen.findByRole('button', { name: 'Working…' })).toBeTruthy()
    expect(box().disabled).toBe(true)
    await act(async () => finish({ kind: 'refusal', rule: 'advice' }))
  })

  it('replaces the run with the new one and writes the explanation after the grid check', async () => {
    askEngine.mockResolvedValue({
      kind: 'run',
      run: NEW_RUN,
      claims: [[{ text: 'Annual return was ' }, { ref: 'backtest.metrics.annual_return', value: 0.128 }, { text: '.' }]],
      dropped: 2,
    })
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    send('a question')
    await screen.findByText('A question typed in the box')
    expect(plain(container)).toContain('Annual return was +12.8%.')
    expect(plain(container)).toContain('2 sentences were left out because they carried a number of their own.')
    expect(plain(container)).toContain('Every number in them comes from the result below.')
    const grid = container.querySelector('#grid-check')!
    const words = container.querySelector('#run-explain')!
    const result = container.querySelector('#run-result')!
    expect(grid.compareDocumentPosition(words) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(words.compareDocumentPosition(result) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('says why a refusal happened and leaves the run on the screen alone', async () => {
    askEngine.mockResolvedValue({ kind: 'refusal', rule: 'advice' })
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    send('what should I buy?')
    await screen.findByText(/does not say what to buy or sell/)
    expect(plain(container)).toContain(EXAMPLE.query)
    expect(container.querySelector('#run-explain')).toBeNull()
  })

  it('says each other failure in words', async () => {
    show()
    await screen.findByText(EXAMPLE.query)
    const cases: [unknown, RegExp][] = [
      [{ kind: 'invalid', problems: ['x'] }, /could not turn this into rules/],
      [{ kind: 'unavailable', reason: 'ANTHROPIC_API_KEY is not set' }, /Questions are not set up on this server yet\..*ANTHROPIC_API_KEY is not set/],
      [{ kind: 'failed', status: 502 }, /could not be answered/],
    ]
    for (const [outcome, pattern] of cases) {
      askEngine.mockResolvedValueOnce(outcome)
      send('again')
      await waitFor(() => expect(screen.getByRole('status').textContent ?? '').toMatch(pattern))
    }
  })

  it('keeps the run and says so when only the explanation failed', async () => {
    askEngine.mockResolvedValue({ kind: 'run', run: NEW_RUN, claims: [], dropped: 0, claimsError: 'model service answered 529' })
    const { container } = show()
    await screen.findByText(EXAMPLE.query)
    send('x')
    await screen.findByText('A question typed in the box')
    expect(plain(container)).toContain('The explanation could not be written. The run itself is below.')
  })

  it('is there even before any run exists, so a first question can create one', async () => {
    fetchSignals.mockResolvedValue(null)
    show()
    await screen.findByText('No run yet.')
    expect(box()).toBeTruthy()
  })
})
