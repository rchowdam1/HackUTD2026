# Eval: batch dev, policy v1.0

Measured: revision c6dd2d1-dirty, arms K,B,C, policy v1.0.

**Scripted transcripts, not ASR.** 40 calls: 20 scam, 20 benign (13 hard-benign).

| Arm | TP | FN | FP | TN | Recall (Wilson 95% CI) | Hard-benign false alerts |
|---|---|---|---|---|---|---|
| K | 20 | 0 | 11 | 9 | 20 of 20 = 100.0% (83.8% to 100.0%) | 11 of 13 (upper bound 95.7%) |
| B | 20 | 0 | 0 | 20 | 20 of 20 = 100.0% (83.8% to 100.0%) | 0 of 13 (upper bound 22.9%) |
| C | 20 | 0 | 0 | 20 | 20 of 20 = 100.0% (83.8% to 100.0%) | 0 of 13 (upper bound 22.9%) |

## Paired B vs K
Correct only under K: 0 (none).
Correct only under B: 11 (dev_benign_01, dev_benign_02, dev_benign_03, dev_benign_04, dev_benign_06, dev_benign_08, dev_benign_09, dev_benign_10, dev_benign_11, dev_benign_12, dev_benign_13).
B wins: 11 one-directional discordant calls, 0 the other way.

## Errors per arm
- K: missed scams: none; false alerts: dev_benign_01, dev_benign_02, dev_benign_03, dev_benign_04, dev_benign_06, dev_benign_08, dev_benign_09, dev_benign_10, dev_benign_11, dev_benign_12, dev_benign_13
- B: missed scams: none; false alerts: none
- C: missed scams: none; false alerts: none

C: 0 intent model calls failed and fell back to arm B.

Percentages: estimates and lower bounds rounded down, upper bounds rounded up. Sample is small; this is not a production accuracy claim.
