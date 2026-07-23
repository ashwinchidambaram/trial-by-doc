# Deck slide 11 — real A/B/C extracts (same region, three readers)

**Source:** run `v1-baseline`, bench `realdoc_qa_scanned_heavy` (heavy scan/fax degradation),
sample `mortgage_q229` — a HUD-27011 "Single-Family Application for Insurance Benefits" form,
**Part B Fiscal Data page, items 101–104** (the header block: FHA case number, section-of-act
code, mortgagee reference number, date prepared). All values are synthetic benchmark data — no
real personal information. Item 100 (borrower name/address) deliberately excluded from the region.

Extracts are **verbatim** — whitespace, garbage characters, and misnumbering untouched.

---

## A — `tesseract` (the incumbent)

```
1a) PHA Case Namber + PRD Seve of At Conte

380-1122334 | 2.03(b)

Name amd Property Address

Creteremie mambet (F529 i eg Tha Date tiem prepat

: GLS- 031326

03-05-2026
```

**What it got wrong:** every label is mangled ("PHA Case Namber", "PRD Seve of At Conte"),
the act code gains a stray digit ("2.03(b)"), the reference number gains a space ("GLS- 031326"),
and the label→value pairing is destroyed — downstream, the frozen B.2 reader working from this
text mapped `FHA_Case_Number=GLS-031326` and picked the wrong date.

## B — `lightonocr` (commodity-GPU vision model)

```
| 101 | FHA Case Number |
| --- | --------------- |
|      | 380-1122334     |

| 102 | Section of Act Code |
| --- | ------------------- |
|      | 203(b)              |

| 103 | Mortgage & reference number (max 15 digits) |
| --- | -------------------------------------------- |
|      | GLS-031326                                   |

| 104 | Exp. date to Submit Title Evidence or fiscal data for Part B |
| --- | ----------------------------------------------------------- |
|      | 03-20-2026                                                  |

| 105 | Date form prepared |
| --- | ------------------ |
|      | 03-05-2026         |
```

**What it got wrong:** all values are correct, but items 104 and 105 are swapped — the form's
item 104 is "Date form prepared" (03-05-2026); lightonocr assigned that label to 105 and put the
title-evidence expiry date under 104. (Its "Mortgage &" for "Mortgagee's" in 103 is also a
transcription slip.)

## C — `olmocr2` (accuracy-leading vision model)

```
101. FHA Case Number
380-1122334

102. Section of Act Code
203(b)

103. Mortgagee's reference number (max 15 digits)
GLS-031326

104. Date form prepared
03-05-2026
```

**What it got wrong:** nothing in this region — labels, numbering, and values all correct.

---

## Ground truth (benchmark gold for this sample)

```
FHA_Case_Number=380-1122334
Section_Of_Act_Code=203(b)
Date_Form_Prepared=2026-03-05
Mortgagee_Reference_Number=GLS-031326
(remaining gold fields on this sample: Check_If_Supplemental=unchecked; Net_Claim_Amount=14915.90)
```

## Per-sample B.1 on this exact sample (from `v1-baseline` raw score records)

| model | B.1 (this sample, 6 gold fields) |
|---|---|
| tesseract | **0.667** |
| lightonocr | **0.833** |
| olmocr2 | **0.833** |

(B.1 is deterministic field-value **presence**: the fraction of this sample's six gold values
that survive verbatim-or-normalized in the OCR markdown, reader-independent. Each VLM lost one
of the six gold values elsewhere on the page — not in the excerpt region above; tesseract lost
two.)

## Traceability

- run: `v1-baseline` · bench: `realdoc_qa_scanned_heavy` (dataset revision `906170ab`,
  deterministic seeded degradation per `results/runs/v1-baseline/manifest.json`)
- sample: `mortgage_q229` (HUD-27011, Part B Fiscal Data page)
- extracts: `results/runs/v1-baseline/predictions/<model>/realdoc_qa_scanned_heavy.jsonl`
- per-sample scores: `results/runs/v1-baseline/raw/<model>/realdoc_qa_scanned_heavy.jsonl`
