import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useStrings } from '../../i18n'
import { isolate } from '../../i18n/format'
import { askEngine } from '../../api/ask'
import type { AskOutcome } from '../../api/ask'
import { strings } from './strings'
import type { RunStrings } from './strings'

export type RunOutcome = Extract<AskOutcome, { kind: 'run' }>

/**
 * One question box. A run replaces the result on the screen; a refusal, an unusable spec or a
 * server that is not set up is said in words and changes nothing else.
 */
export function AskBox({ onRun }: { onRun: (outcome: RunOutcome) => void }) {
  const s = useStrings<RunStrings>(strings)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const pending = useRef<AbortController | null>(null)

  useEffect(() => () => pending.current?.abort(), [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (!text || busy) return
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setBusy(true)
    setNote(null)
    const outcome = await askEngine(text, controller.signal)
    if (controller.signal.aborted) return
    setBusy(false)
    if (outcome.kind === 'run') onRun(outcome)
    else if (outcome.kind === 'refusal') setNote(s(`refusal_${outcome.rule}` as const))
    else if (outcome.kind === 'invalid') setNote(s('askInvalid'))
    else if (outcome.kind === 'unavailable') setNote(`${s('askUnavailable')}${outcome.reason ? ` ${isolate(outcome.reason)}` : ''}`)
    else setNote(s('askFailed'))
  }

  return (
    <form onSubmit={submit} className="mt-5" aria-busy={busy}>
      <label htmlFor="run-ask" className="text-sm text-muted">
        {s('askLabel')}
      </label>
      <div className="mt-1 flex items-center gap-2">
        <input
          id="run-ask"
          type="text"
          value={question}
          maxLength={500}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={s('askPlaceholder')}
          disabled={busy}
          className="panel min-h-11 min-w-0 flex-1 px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="min-h-11 shrink-0 rounded-full border border-line px-4 text-sm active:bg-fg/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fg disabled:opacity-50"
        >
          {busy ? s('asking') : s('askButton')}
        </button>
      </div>
      <p role="status" className="mt-2 text-sm leading-snug text-muted">
        {note}
      </p>
    </form>
  )
}
