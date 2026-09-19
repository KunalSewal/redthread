# Fraud Policy v1.0 — Cheat Sheet

Condensed from `data/README.md` ("Fraud Policy" and "Answer Format"). The README is authoritative;
it is a provided file and does not change, so this summary should not drift. Cite rule numbers in
every `reason`.

## Actions and approval routes

| Action | Route |
|---|---|
| `ALLOW_TRANSACTION`, `MONITOR_CARD`, `MONITOR_CONNECTED_CARDS`, `WARN_CUSTOMER`, `VERIFY_WITH_CUSTOMER`, `STEP_UP_AUTH`, `GENERATE_REPORT`, `CREATE_CASE`, `ESCALATE_TO_ANALYST`, `CLOSE_NO_FRAUD` | `auto` |
| `DECLINE_TRANSACTION` | `L1` |
| `BLOCK_CARD`, exposure ≤ $2,500 | `L1` |
| `BLOCK_CARD`, exposure > $2,500 | `L2` |
| `BLOCK_ALL_CARDS` | `L2` |
| `FILE_REPORT` | `L2` |

Only `auto` actions may be executed by the agent. L1/L2 are recommended and wait for a human.
Order actions by what happens first.

## Rules

- **R1** Single signal (incl. risk score alone) and p < 0.70: `VERIFY_WITH_CUSTOMER` or `STEP_UP_AUTH` before any block.
- **R2** Customer denies: `BLOCK_CARD` + `CREATE_CASE`; add `FILE_REPORT` if exposure > $1,000 or linked to a shared device profile / another card's fraud.
- **R3** Customer confirms: `CLOSE_NO_FRAUD`, note it in the case.
- **R4** No reply in 24h: `MONITOR_CARD` + `DECLINE_TRANSACTION` for pending auths; escalate if exposure > $500.
- **R5** Card testing (≥3 small online auths within 1h, then a larger purchase): `DECLINE_TRANSACTION` + `STEP_UP_AUTH`; if a purchase > $100 already cleared, `BLOCK_CARD`.
- **R6** Shared origin (several cards with fraud from same device profile / billing region / recipient email in one window): name it; `CREATE_CASE`, `FILE_REPORT`, `MONITOR_CONNECTED_CARDS`.
- **R7** Disputed but matches own recurring pattern (same merchant/amount, monthly): `CREATE_CASE`, `VERIFY_WITH_CUSTOMER`, `WARN_CUSTOMER`. Do not block.
- **R8** Verdict `uncertain` and exposure > $500, or evidence conflicts: `ESCALATE_TO_ANALYST`.
- **R9** Undocumented but coordinated/repeated abuse across customers: `CREATE_CASE`, `FILE_REPORT`, `ESCALATE_TO_ANALYST`; describe in own words.
- **R10** Never `BLOCK_ALL_CARDS` unless ≥2 of the customer's cards have confirmed fraud or credentials are confirmed compromised.

## Case vs SAR (3a)

- **Open a case** when p ≥ 0.30, whenever evidence is requested, or whenever a customer disputes.
- **File a SAR** when fraud is confirmed or strongly suspected **and** any of: exposure > $1,000;
  connects to a shared device profile / region cluster / another customer's fraud; coordinated or
  undocumented (R9). A SAR always has a case behind it. Most cases need no SAR.
- SAR narrative: 6–12 sentences, stands alone: who, what, when, where, how, why suspicious.

## Evidence, stopping, exposure

- Evidence requests (`customer_validation` | `step_up_auth` | `analyst_info`) need no approval.
  Responses are **simulated**; record the assumption in `evidence_requests[].assumed_response`.
- **Stop** when p ≥ 0.85 or ≤ 0.15 with ≥2 independent pieces of evidence, or a verification response
  settles it, or further steps would not change the decision (say so in `stop_reason`).
- **Exposure** = sum of |amount| over `affected_txn_ids`, including the flagged txn.
- `legitimate` verdict: `affected_txn_ids` empty, `exposure_usd` 0, `sar.file` false.
- If nothing was requested, `final` equals `initial` and `what_changed` is `"nothing"`.

## Pattern enum

`card_testing` · `card_not_present_fraud` · `card_not_present_new_device` · `out_of_region_use` ·
`account_takeover` · `undocumented` (requires `pattern_description`) · `none`

## Case status / verdict enums

status: `open` | `closed_fraud` | `closed_legitimate` | `escalated`
verdict: `fraud` | `legitimate` | `uncertain`
evidence.source: `graph` | `document` | `customer` | `external`
