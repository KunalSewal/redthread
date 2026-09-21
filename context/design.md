# The workbench: design notes

Why the interface looks the way it does. Read this before changing tokens, colour meaning, or the
thread.

## What this is

A fraud analyst's workbench for an agent that investigates card-fraud alerts on a graph. Two
audiences: an analyst who has to defend a decision to a regulator, and a reviewer who has three to
five minutes to judge whether the agent reasons or merely asserts. Both need the same thing, which is
why there is one interface and not a "demo mode": **the reasoning has to be inspectable, step by
step, and reversible.**

## The idea

A case file on an analyst's desk, late. The desk is cool and dark; the sheet on it is warmer and
lifted. Nothing glows. The only saturated thing in the room is the thread.

## Colour

Sampled from `references/` (TigerGraph orange and its dark neutral) and set against the dark treatment
both tigergraph.com and hhgoa.com use.

| Token | Value | Job |
|---|---|---|
| `--desk` | `#0E1218` | the surface everything rests on, cool blue-black |
| `--sheet` | `#171C24` | the case sheet |
| `--sheet-raised` | `#1E242E` | panels lifted off the sheet |
| `--rule` | `#2A3240` | hairlines, never a border for decoration |
| `--ink` | `#E8EBF0` | primary text |
| `--graphite` | `#9AA5B5` | secondary text, meets AA on sheet |
| `--thread` | `#FF6D00` | **fraud identity, and nothing else** |
| `--thread-dim` | `#8A4310` | the thread behind the playhead, already walked |
| `--cleared` | `#69B3A2` | a cleared outcome, deliberately muted |
| `--focus` | `#7AA2F7` | keyboard focus only |

**The one rule that matters: orange encodes fraud.** Confirmed-fraud cases, affected and connected
entities, the investigation thread. It never means "selected", "primary button", "current tab" or "a
series in a chart". If everything can be orange, orange says nothing. Uncertain gets no hue at all —
a neutral outline and a glyph — so it cannot compete with the accent, and categorical distinction in
charts comes from stroke style and direct labels rather than legend swatches.

## Type

**Archivo** for interface, labels and every number: a sturdy grotesque with an industrial edge and
numerals that hold a column. **Newsreader** for narrative prose — the case summary, the SAR, analyst
notes, retrieved policy — because those are documents a person reads, not data they scan. Tabular
figures everywhere money or probability appears. No tracked-out capital eyebrows, no monospace for
small labels, no arrows appended to buttons.

## Layout and the signature interaction

The case sheet holds prose at a ~68ch measure. Down its left edge runs the thread: a continuous line
with one node per investigation step.

**The thread is a scrubber.** `←`/`→` (or dragging the playhead) rewinds the whole case file to that
step: the evidence graph shows only the entities known by then, the probability scale shows where
belief stood, the evidence digest swaps to the tool that ran, and the action plan shows the plan as
of then. One control drives five views, which is what turns the required narrative into a single
continuous move instead of a tour of tabs.

Honesty constraint: belief is genuinely known at only three points (the first assessment, and the
prior and posterior around the customer's reply). The scale draws an explicit "no estimate yet"
region rather than interpolating a curve we did not measure.

## Restraint

Boldness is spent in one place: the thread. Everything around it is quiet — hairlines, no shadows, no
card kit, no gradient washes, no entrance animation on every section. Motion answers actions only:
the graph assembles as steps advance, because that shows what changed.

## Quality floor

Responsive to 390px, visible keyboard focus with roving tabindex on the thread, reduced motion
respected in behaviour and not only in CSS, AA contrast on every text colour actually used, a print
stylesheet for the case file, and graceful degradation for monitoring traces, which have no
assessment, report or customer reply.
