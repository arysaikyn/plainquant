import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { askEngine } from './ask'

const EXAMPLE = JSON.parse(readFileSync(resolve(process.cwd(), '../model/signals.example.json'), 'utf8'))
const CLAIMS = [[{ text: 'Annual return was ' }, { ref: 'backtest.metrics.annual_return', value: 0.128 }]]

function reply(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ status, ok: status >= 200 && status < 300, json: async () => body })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('askEngine', () => {
  it('posts the question as JSON to the ask route', async () => {
    const f = reply(200, { refusal: 'advice' })
    await askEngine('cheap names')
    const [url, init] = f.mock.calls[0]
    expect(url).toBe('/api/engine/ask')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ question: 'cheap names' })
  })

  it('reads a run: the result is parsed with the same parser as /ai, the claims as segments', async () => {
    reply(200, { result: EXAMPLE, claims: CLAIMS, dropped: 2 })
    const out = await askEngine('q')
    expect(out.kind).toBe('run')
    if (out.kind === 'run') {
      expect(out.run.query).toBe(EXAMPLE.query)
      expect(out.claims).toEqual(CLAIMS)
      expect(out.dropped).toBe(2)
    }
  })

  it('keeps the reason when only the explanation failed', async () => {
    reply(200, { result: EXAMPLE, claims: [], dropped: 0, claims_error: 'model service answered 529' })
    const out = await askEngine('q')
    expect(out.kind === 'run' && out.claimsError).toBe('model service answered 529')
  })

  it('reads each refusal rule the product names', async () => {
    for (const rule of ['execution', 'guarantee', 'advice']) {
      reply(200, { refusal: rule })
      expect(await askEngine('q')).toEqual({ kind: 'refusal', rule })
    }
  })

  it('does not accept a refusal rule it does not know', async () => {
    reply(200, { refusal: 'vibes' })
    expect((await askEngine('q')).kind).toBe('failed')
  })

  it('reads the problems of an unusable spec', async () => {
    reply(422, { detail: 'x', problems: ['rank: too short', 3] })
    expect(await askEngine('q')).toEqual({ kind: 'invalid', problems: ['rank: too short'] })
  })

  it('treats a 422 without problems (a bad question) as a failure, not as an invalid spec', async () => {
    reply(422, { detail: 'the question must be 1 to 500 characters' })
    expect(await askEngine('q')).toEqual({ kind: 'failed', status: 422 })
  })

  it('says when the server is not set up, with its reason', async () => {
    reply(503, { detail: 'ANTHROPIC_API_KEY is not set' })
    expect(await askEngine('q')).toEqual({ kind: 'unavailable', reason: 'ANTHROPIC_API_KEY is not set' })
  })

  it('maps a provider failure and a network failure to failed', async () => {
    reply(502, { detail: 'model service answered 401' })
    expect(await askEngine('q')).toEqual({ kind: 'failed', status: 502 })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    expect(await askEngine('q')).toEqual({ kind: 'failed', status: 0 })
  })

  it('refuses a result or claims it cannot read', async () => {
    reply(200, { result: { ...EXAMPLE, audit: undefined }, claims: [], dropped: 0 })
    expect((await askEngine('q')).kind).toBe('failed')
    reply(200, { result: EXAMPLE, claims: [[{ nope: 1 }]], dropped: 0 })
    expect((await askEngine('q')).kind).toBe('failed')
    reply(200, { result: EXAMPLE, claims: 'text', dropped: 0 })
    expect((await askEngine('q')).kind).toBe('failed')
  })
})
