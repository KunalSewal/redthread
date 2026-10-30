import type { ReplayStep } from '@/lib/api'
import { action, sentence } from '@/lib/format'

/* Each replay step in plain words: a short title for the list, and why the agent took it. */

const TOOLS: Record<string, { title: string; why: string }> = {
  alert_context: {
    title: 'Read the flagged charge',
    why: 'It starts from the transaction the alert names: the charge itself, the card, the customer and what the bank already knows about them.',
  },
  card_activity: {
    title: "Looked at the card's charges",
    why: 'It reads the charges around the alert to see what this card normally does and what changed.',
  },
  activity_shift: {
    title: 'Checked for something new',
    why: 'It looks for charges of a kind this card had almost never made before: the first sign of a scheme that a single score misses.',
  },
  scheme_peers: {
    title: 'Looked for others doing the same',
    why: "If other customers' cards started the same new thing in the same 30 days, and not before, this is a scheme, not one card.",
  },
  holder_baseline: {
    title: "Compared with the holder's history",
    why: 'It checks the charge against the account holder’s own past: amounts, regions, products and channels.',
  },
  shared_origin: {
    title: 'Checked where the charge came from',
    why: 'It asks whether the device, region or email behind the charge is shared with known fraud more than usual.',
  },
  linked_cases: {
    title: 'Looked for linked past cases',
    why: 'Past cases on the same card, device or customer are precedent: what the bank concluded before.',
  },
  similar_cases: {
    title: 'Searched for similar past cases',
    why: 'It searches the 5,585 closed cases for ones that read like this one, and what they turned out to be.',
  },
  community: {
    title: "Checked the card's wider community",
    why: 'It looks at the group of cards this one moves among in the graph, and how much fraud that group carries.',
  },
  device_check: {
    title: 'Looked at the device behind it',
    why: 'It checks how many other cards used the same device in the same window, and whether any were fraud.',
  },
  policy: {
    title: 'Read the fraud policy',
    why: 'It looks up the policy passages that apply, so every recommendation can cite its rule.',
  },
  policy_rule: {
    title: 'Cited a policy rule',
    why: 'It attaches the exact rule behind a recommended action, so the action can be checked against policy.',
  },
  regulatory_redflags: {
    title: 'Checked regulatory guidance',
    why: 'It matches the activity against published red flags from FinCEN, FFIEC, FATF and OFAC.',
  },
}

const KINDS: Record<string, { title: string; why: string }> = {
  alert: { title: 'The alert arrives', why: 'This is what the bank sent. Everything after this is the agent’s own work.' },
  quarantined: {
    title: 'Set aside hidden instructions',
    why: 'Part of the alert text was written to the agent, not to an analyst. It is removed before the model sees it, and never acted on.',
  },
  assessment: {
    title: 'Weighed the evidence',
    why: 'The model judged each finding; code combined those judgements into a probability, starting from how often alerts like this were fraud before.',
  },
  recommendation: {
    title: 'Recommended actions',
    why: 'The policy engine turns the verdict and evidence into actions, and says which ones need a person to approve.',
  },
  case_opened: {
    title: 'Opened a case in the graph',
    why: 'The case is written into the graph as soon as the policy calls for one, so the next investigation can find it.',
  },
  request: { title: 'Asked for more evidence', why: 'The picture was not decisive, so it asked the customer or an analyst before deciding.' },
  reply: { title: 'Got a reply', why: 'The reply is weighed like any other evidence, and the plan can change because of it.' },
  report: { title: 'Wrote the report', why: 'It writes the case summary and, where the policy requires one, the suspicious activity report.' },
  memory: {
    title: 'Updated the case in the graph',
    why: 'The final status and actions are written back, so later investigations read this case as memory.',
  },
  model_reused: { title: 'Reused a stored answer', why: 'The same question was asked before, so the stored model answer was reused and recorded.' },
  model_degraded: { title: 'Model stepped down', why: 'After two timeouts the model was asked to think less, and the case records that.' },
  halted: { title: 'Stopped', why: 'Something failed, so it stopped without writing an answer.' },
}

export function describe(step: ReplayStep) {
  if (step.kind === 'evidence' && step.tool && TOOLS[step.tool]) return TOOLS[step.tool]
  if (step.kind === 'evidence' && !step.tool) return { title: 'Grounded its citations', why: 'Each cited rule is tied to the passage it comes from.' }
  return KINDS[step.kind] ?? { title: sentence(step.kind.replaceAll('_', ' ')), why: '' }
}

/** "Initial: BLOCK_CARD (L1), CREATE_CASE (auto)" as plain actions. */
export function parseActions(detail: string) {
  return [...detail.matchAll(/([A-Z_]{4,}) \((auto|L1|L2)\)/g)].map((m) => ({ label: action(m[1]), route: m[2] }))
}

const SKIP = new Set(['note', 'how_to_read', 'definition', 'omitted_note', 'shown_rows', 'rows', 'window'])

/** A few readable facts from what a query returned, without dumping the raw data. */
export function facts(returned: Record<string, unknown> | undefined) {
  if (!returned) return []
  const out: { label: string; value: string }[] = []
  for (const [k, v] of Object.entries(returned)) {
    if (SKIP.has(k) || v == null || out.length >= 8) continue
    const label = sentence(k.replaceAll('_', ' ').replace(/\bn /, 'number of ').replace(/\busd\b/, '($)'))
    if (typeof v === 'number') out.push({ label, value: fmtNumber(k, v) })
    else if (typeof v === 'boolean') out.push({ label, value: v ? 'Yes' : 'No' })
    else if (typeof v === 'string') out.push({ label, value: v.length > 90 ? `${v.slice(0, 90)}…` : v })
    else if (Array.isArray(v)) out.push({ label, value: v.length === 0 ? 'None' : `${v.length}` })
    else if (typeof v === 'object' && 'count' in (v as object)) out.push({ label, value: String((v as { count: number }).count) })
  }
  return out
}

function fmtNumber(key: string, v: number) {
  if (/rate|share|score|lift/.test(key) && v <= 1 && v >= 0 && !Number.isInteger(v)) return `${(v * 100).toFixed(1)}%`
  if (/usd|amount/.test(key)) return `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  return v.toLocaleString('en-US', { maximumFractionDigits: 3 })
}
