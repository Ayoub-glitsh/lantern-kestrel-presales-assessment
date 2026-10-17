# Walkthrough — Design Tradeoff and Verification Check

*Equivalent accessible text in lieu of a recorded walkthrough. Estimated reading time: 3–4 minutes.*

---

## Design Tradeoff — MR scan plan: `mobile-static` vs `mobile-full`

The most consequential design decision in this integration is the choice of scan plan for
the merge request pipeline.

Rafa asked that every MR introducing a high or critical finding be blocked before merge (R1).
The natural answer would be `mobile-full` — static and dynamic analysis — because it gives
the most complete coverage. But `mobile-full` takes 20 to 45 minutes (P9), and by the time
the Android debug build finishes, the MR pipeline has already used 13 of its 15-minute
budget (lint 2 min + unit tests 5 min + build 6 min). Running `mobile-full` with `--wait`
would cause every single MR to time out, making the gate both unusable and unreliable.

The tradeoff I made is to use `mobile-static` on MR — static analysis only — and accept that
dynamic findings will not be caught at the MR stage. This is a real gap: a vulnerability
that only manifests at runtime would pass through the MR gate. The mitigation is layered
coverage: the nightly pipeline runs `mobile-full` every night on `main`, so dynamic findings
surface within 24 hours of a merge, and the release gate runs `mobile-full` with a baseline
before any build reaches production. No high or critical finding — static or dynamic — can
reach a release without being caught.

I chose this tradeoff over the alternative (removing `--wait` on MR and just submitting
without blocking) because submitting without `--wait` always exits 0 (P5), which would give
a false sense of security — the MR would turn green before any result is available. A
`mobile-static` scan with `--wait` and `--fail-on high` is a real gate, even if it covers
less than `mobile-full`.

---

## Verification Check — S01 exit code and label

S01 is the scenario most likely to produce the wrong label on a quick read, so I used it as
my primary verification check.

The scenario is a release gate on the Android AAB for release 4.12.0. The scan returns three
findings: F-101 (high, open), F-102 (medium, open), F-103 (low, open). At first glance,
F-101 looks like it should trigger exit 1 and a `block` label — it is high severity and open
status, both conditions for counting.

The check I ran was to compare F-101's fingerprint (`fp-and-01`) against the baseline
fingerprints listed in the scenario. The baseline `rel-4.11-android` contains `[fp-and-01,
fp-and-02]`. F-101's fingerprint is in the baseline — it is excluded by baseline (P7) and
does not count. F-102 and F-103 are below the high threshold. Counted findings: zero. Exit
code: 0. Label: `pass`.

This check confirmed that the baseline exclusion logic must be applied before the exit-code
threshold check — not after. A finding can look alarming on paper but produce no gate action
if it was already accepted in the previous release. That is exactly the behaviour Imane asked
for in R4, and it is what `--baseline` delivers.

I applied the same per-finding verification to all nine scenarios before assigning any label,
which is why the batch analysis takes the form of an explicit table rather than a summary.
