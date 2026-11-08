# Eval: batch H1, policy v1.0

Measured: revision 36ae5c4, arms K,B, policy v1.0.

**Scripted transcripts, not ASR.** 60 calls: 30 scam, 30 benign (22 hard-benign).

| Arm | TP | FN | FP | TN | Recall (Wilson 95% CI) | Hard-benign false alerts |
|---|---|---|---|---|---|---|
| K | 27 | 3 | 13 | 17 | 27 of 30 = 90.0% (74.3% to 96.6%) | 13 of 22 (upper bound 76.8%) |
| B | 18 | 12 | 0 | 30 | 18 of 30 = 60.0% (42.3% to 75.5%) | 0 of 22 (upper bound 14.9%) |

## Paired B vs K
Correct only under K: 9 (h1_scam_03, h1_scam_06, h1_scam_07, h1_scam_14, h1_scam_16, h1_scam_18, h1_scam_19, h1_scam_29, h1_scam_30).
Correct only under B: 13 (h1_benign_01, h1_benign_02, h1_benign_03, h1_benign_04, h1_benign_06, h1_benign_08, h1_benign_11, h1_benign_12, h1_benign_14, h1_benign_15, h1_benign_17, h1_benign_19, h1_benign_22).
No win called: needs 5 or more discordant calls all in one direction (have K-only 9, B-only 13).

## Errors per arm
- K: missed scams: h1_scam_04, h1_scam_05, h1_scam_23; false alerts: h1_benign_01, h1_benign_02, h1_benign_03, h1_benign_04, h1_benign_06, h1_benign_08, h1_benign_11, h1_benign_12, h1_benign_14, h1_benign_15, h1_benign_17, h1_benign_19, h1_benign_22
- B: missed scams: h1_scam_03, h1_scam_04, h1_scam_05, h1_scam_06, h1_scam_07, h1_scam_14, h1_scam_16, h1_scam_18, h1_scam_19, h1_scam_23, h1_scam_29, h1_scam_30; false alerts: none

Percentages: estimates and lower bounds rounded down, upper bounds rounded up. Sample is small; this is not a production accuracy claim.
