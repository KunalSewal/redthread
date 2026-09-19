# Data Dictionary

Full column descriptions are in `data/README.md`. This file records what we verified by profiling
(2026-09-19) and the derivations the loader relies on. **Do not open the big CSVs with Read/cat.**

## Files

| File | Rows | Size | Notes |
|---|---|---|---|
| `data/transactions.csv` | 590,742 | 708 MB | 397 columns: 393 Vesta + `customer_id`, `ts`, `channel`, `risk_score`. No fraud label |
| `data/identity.csv` | 144,432 | 27 MB | 41 columns, joins on `TransactionID`. Online only |
| `data/closed_cases_history.csv` | 5,565 | 2.7 MB | Labeled memory, opened 2016-07-02 to 2016-11-02 |
| `data/case_pack.csv` | 20 | 4 KB | The exam. Opened 2016-11-12 to 2016-12-29 |

## Verified facts: transactions

- `ts` range 2016-07-02 to 2016-12-31. Monthly counts: Jul 130k, Aug 94k, Sep 93k, Oct 100k,
  **Nov 85k, Dec 89k (exam period)**.
- 13,553 customers. **`customer_id` maps 1:1 to `card1`.**
- `channel`: `in_person` 439,670 (all `ProductCD = W`), `online` 151,072 (C, R, H, S).
  95.6% of online transactions have an identity record.
- `risk_score`: mean 0.17, median 0.12, p75 0.22, max 0.99. 16,871 transactions score > 0.7.
- `card6`: debit 440k, credit 149k, null 1,571, "debit or credit" 30, "charge card" 15.
- `card4`: visa 385k, mastercard 189k, amex 8.3k, discover 6.7k, null 1,577.
- `addr2` = billing country (87 = home). `addr1` = billing region; null for many online txns.

## Card ID derivation (not a column; must be computed)

Case files use card IDs like `C12382-K1`, but `transactions.csv` has no `card_id`.
Verified rule, **100% match on all 14,975 labeled transactions** (every closed-case txn + the 20 flagged txns):

```
key      = str(card6)                      # null becomes the string "None"
rank     = 1-based position of key among the customer's distinct keys, sorted as plain strings
card_id  = f"{customer_id}-K{rank}"
```

Because `"None"` sorts before lowercase words, null-card rows get K1 when present.
Result: 14,317 cards (K1 200,576 txns, K2 389,259, K3 907).

Open item: keying on `(card4, card6)` also gives 100% on labeled rows but differs from `card6`-only
on 8 unlabeled rows (14,318 cards). Use `card6`-only unless a case ID contradicts it; revisit if so.
Implement this once in the loader and unit-test it against the closed cases.

## Customers are issuer buckets; holders are the real people

`customer_id` is the IEEE `card1` issuer code, so one "customer" can hold hundreds of unrelated
people's transactions across dozens of regions (C12382: 422 txns, 40+ regions). Naive "cardholder
history" signals (new region, unusual amount) fire constantly on that crowd.

**Holder** = `card_id | billing region | anchor day`, where anchor day = `floor(TransactionDT / 86400) - D1`
(D1 counts days since the card's first use, so the anchor is constant for one holder).
Implemented in `redthread.data.entities.holder_ids`. 222,481 holders; many are single-transaction
because online txns often lack a region. Use holder history for "is this normal for this person",
and card history only as context. Example: HHG-001's flagged $77.07 in region 444 shares its holder
with $77.08 (Nov 26) and $77.05 (Dec 11): a weekly recurring purchase.

## Labels and the fraud model

- Confirmed-fraud closed cases cover **3.37% of Jul–Oct transactions**, matching the original
  dataset's fraud rate, so the closed cases are an essentially complete label set for Jul–Oct.
- Bank `risk_score` on Jul–Oct: AUC 0.85; fraud share by band: <0.1: 0.5%, 0.5–0.7: 18%,
  0.7–0.85: 25%, >0.85: 37%. Useful but noisy, as the README warns.
- `scripts/train_model.py` trains LightGBM on all Vesta features plus holder aggregates.
  Train Jul–Sep, test Oct: **AUC 0.968, average precision 0.64** (bank score: 0.87 / 0.25).
  Scores: Nov–Dec from a Jul–Oct model; Jul–Oct out-of-fold by month (AUC 0.970, AP 0.76).
  Stored as `Txn.model_score` (-1 = missing). It is evidence, not a verdict, like the risk score.

## Verified facts: identity

- `id_15` (device New/Found for this account): Found 67,773, New 61,754, Unknown 11,653, null 3,252.
- `id_23` (proxy): transparent 3,492, anonymous 1,185, hidden 611, null for the rest.
- **Device profile** = `DeviceInfo | id_30 (OS) | id_31 (browser) | id_33 (screen)`, as in the
  README example, nulls rendered `unknown`. 9,705 profiles (one all-null combination excluded),
  IDs `D000001…` in order of first use.
- **Device specificity matters.** Median profile is used by 1 card; max 842. Partial profiles like
  `unknown | unknown | chrome 66.0 | unknown` are shared by hundreds of cards and are not evidence of
  a link. Weight device links by `DeviceProfile.n_cards`.
- The undocumented ring device from the closed cases is **D004630** (SAMSUNG SM-G935F, anonymous
  proxy). HHG-014's flagged transaction is on it.

## Verified facts: closed cases

| Outcome | Pattern | Count |
|---|---|---|
| confirmed_fraud | card_not_present_fraud | 1,404 |
| confirmed_fraud | account_takeover | 1,205 |
| confirmed_fraud | card_not_present_new_device | 1,076 |
| confirmed_fraud | out_of_region_use | 955 |
| confirmed_fraud | card_testing | 16 |
| confirmed_fraud | undocumented | 9 |
| cleared | none | 900 |

- `actions_taken` has only three values: `CREATE_CASE|BLOCK_CARD` (4,268),
  `CREATE_CASE|BLOCK_CARD|FILE_REPORT` (397), `VERIFY_WITH_CUSTOMER|CLOSE_NO_FRAUD` (900).
- Cleared cases have `first_fraud_txn_id` null but `txn_ids` set to the alerted transaction.
  Their notes give the false-alarm reason (e.g. new phone confirmed, travel confirmed).
- Only 4 cases have `connected_card_ids`.
- **Undocumented cases** describe the same device profile (Samsung SM-G935F, Chrome for Android,
  anonymous proxy, New to the account) used across several cardholders in one month. That is a
  shared-device ring; HHG-014 (the analyst request about "the same unusual device profile") is likely related.
  README warns there are more undocumented patterns than this one.

## Case pack observations

- Triggers: 11 risk_score, 8 customer_report, 1 analyst_request.
- Flagged txns: 5 in person (W), 15 online. Several online flagged txns have null `addr1`.
- The flagged txn is where the alert fired, not necessarily where fraud started.
- "I never made this purchase" can be pattern R7 (disputed but legitimate recurring charge). Check
  the card's history for same amount/product monthly before assuming fraud.

## Unnamed features

V1–V339, C1–C14, D1–D15, M1–M9, id_01–id_11 are real model features with no names. They can be
signals, but evidence must describe them honestly ("Vesta feature D1 is 0"), not invent meanings.
