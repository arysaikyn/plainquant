import { parseSignals } from './signals'
import type { Signals } from './signals'

/**
 * The ask path of the backend (`POST /api/engine/ask`): a question in, a run and its
 * explanation out. The explanation arrives as segments, not as text with numbers in it: a
 * sentence is a list of words and references, and the value of a reference is the engine's.
 * The screen formats it, so the language model never wrote a digit the reader sees.
 */

export type Scalar = string | number | boolean | null
export type Segment = { text: string } | { ref: string; value: Scalar }
export type Rule = 'execution' | 'guarantee' | 'advice'

export type AskOutcome =
  | { kind: 'run'; run: Signals; claims: Segment[][]; dropped: number; claimsError?: string }
  | { kind: 'refusal'; rule: Rule }
  | { kind: 'invalid'; problems: string[] }
  | { kind: 'unavailable'; reason: string }
  | { kind: 'failed'; status: number }

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''
const RULES: readonly Rule[] = ['execution', 'guarantee', 'advice']

function isScalar(v: unknown): v is Scalar {
  return v === null || ['string', 'number', 'boolean'].includes(typeof v)
}

function parseSegments(raw: unknown): Segment[][] {
  if (!Array.isArray(raw)) throw new Error('claims')
  return raw.map((claim) => {
    if (!Array.isArray(claim)) throw new Error('claim')
    return claim.map((part): Segment => {
      const p = part as Record<string, unknown>
      if (p && typeof p.text === 'string') return { text: p.text }
      if (p && typeof p.ref === 'string' && isScalar(p.value)) return { ref: p.ref, value: p.value }
      throw new Error('segment')
    })
  })
}

export async function askEngine(question: string, signal?: AbortSignal): Promise<AskOutcome> {
  let response: Response
  try {
    response = await fetch(`${BASE}/api/engine/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch {
    return { kind: 'failed', status: 0 }
  }
  let body: Record<string, unknown> = {}
  try {
    body = (await response.json()) as Record<string, unknown>
  } catch {
    // an unreadable body is handled by the status below
  }
  if (response.status === 503) return { kind: 'unavailable', reason: typeof body.detail === 'string' ? body.detail : '' }
  if (response.status === 422 && Array.isArray(body.problems)) {
    return { kind: 'invalid', problems: body.problems.filter((p): p is string => typeof p === 'string') }
  }
  if (!response.ok) return { kind: 'failed', status: response.status }
  if (typeof body.refusal === 'string' && (RULES as readonly string[]).includes(body.refusal)) {
    return { kind: 'refusal', rule: body.refusal as Rule }
  }
  try {
    return {
      kind: 'run',
      run: parseSignals(body.result),
      claims: parseSegments(body.claims),
      dropped: typeof body.dropped === 'number' ? body.dropped : 0,
      claimsError: typeof body.claims_error === 'string' ? body.claims_error : undefined,
    }
  } catch {
    return { kind: 'failed', status: response.status }
  }
}
