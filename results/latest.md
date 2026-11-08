# Eval: batch H1, policy v1.0

**Scripted transcripts, not ASR.** 60 calls: 30 scam, 30 benign (22 hard-benign).

| Arm | TP | FN | FP | TN | Recall (Wilson 95% CI) | Hard-benign false alerts |
|---|---|---|---|---|---|---|
| K | 9 | 21 | 6 | 24 | 9 of 30 = 30.0% (16.6% to 47.9%) | 6 of 22 (upper bound 48.2%) |
| B | 5 | 25 | 0 | 30 | 5 of 30 = 16.6% (7.3% to 33.6%) | 0 of 22 (upper bound 14.9%) |
| C | 5 | 25 | 1 | 29 | 5 of 30 = 16.6% (7.3% to 33.6%) | 1 of 22 (upper bound 21.8%) |

## Paired B vs K
Correct only under K: 4 (h1_scam_07, h1_scam_18, h1_scam_20, h1_scam_25).
Correct only under B: 6 (h1_benign_01, h1_benign_02, h1_benign_06, h1_benign_12, h1_benign_15, h1_benign_17).
No win called: needs 5 or more discordant calls all in one direction (have K-only 4, B-only 6).

## Errors per arm
- K: missed scams: h1_scam_03, h1_scam_04, h1_scam_05, h1_scam_06, h1_scam_08, h1_scam_09, h1_scam_10, h1_scam_12, h1_scam_14, h1_scam_15, h1_scam_16, h1_scam_17, h1_scam_19, h1_scam_21, h1_scam_22, h1_scam_23, h1_scam_24, h1_scam_26, h1_scam_28, h1_scam_29, h1_scam_30; false alerts: h1_benign_01, h1_benign_02, h1_benign_06, h1_benign_12, h1_benign_15, h1_benign_17
- B: missed scams: h1_scam_03, h1_scam_04, h1_scam_05, h1_scam_06, h1_scam_07, h1_scam_08, h1_scam_09, h1_scam_10, h1_scam_12, h1_scam_14, h1_scam_15, h1_scam_16, h1_scam_17, h1_scam_18, h1_scam_19, h1_scam_20, h1_scam_21, h1_scam_22, h1_scam_23, h1_scam_24, h1_scam_25, h1_scam_26, h1_scam_28, h1_scam_29, h1_scam_30; false alerts: none
- C: missed scams: h1_scam_03, h1_scam_04, h1_scam_05, h1_scam_06, h1_scam_07, h1_scam_08, h1_scam_09, h1_scam_10, h1_scam_12, h1_scam_14, h1_scam_15, h1_scam_16, h1_scam_17, h1_scam_18, h1_scam_19, h1_scam_20, h1_scam_21, h1_scam_22, h1_scam_23, h1_scam_24, h1_scam_25, h1_scam_26, h1_scam_28, h1_scam_29, h1_scam_30; false alerts: h1_benign_12

Percentages: estimates and lower bounds rounded down, upper bounds rounded up. Sample is small; this is not a production accuracy claim.
