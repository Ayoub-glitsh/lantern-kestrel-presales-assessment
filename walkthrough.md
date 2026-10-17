# Walkthrough — Design Tradeoff and Verification Check

*Equivalent accessible text in lieu of a recorded walkthrough. Estimated reading time: 3–4 minutes.*

---

## Design Tradeoff — MR scan plan: `mobile-static` vs `mobile-full`

So the first thing that jumped out when I read Rafa's request R1 was "block every MR on high
or critical" — which sounds simple until you look at the time budget.

By the time the Android debug build finishes, the MR pipeline has already eaten 13 of its
15 minutes. Lint takes 2, unit tests take 5, the build takes 6. That leaves 2 minutes. A
`mobile-full` scan takes anywhere from 20 to 45 minutes. So if I just dropped it in with
`--wait`, every single MR would time out, every time. That's not a gate — that's just a
broken pipeline.

I thought about removing `--wait` and just submitting the scan without blocking. But that
always exits 0 (P5), which means the MR goes green before any result is back. That's the
worst of both worlds — you think you have security coverage but you actually have nothing.

So I went with `mobile-static`. It's static analysis only, it fits in the budget, and it
still catches the majority of high and critical findings. Yes, there's a gap — anything that
only shows up at runtime won't be caught on MR. But I'm comfortable with that tradeoff
because the nightly runs `mobile-full` every night, so dynamic findings surface within 24
hours of a merge. And the release gate runs `mobile-full` with a baseline before anything
ships. Nothing gets to production without full coverage.

---

## Verification Check — S01, why I almost got it wrong

S01 is the one I'd flag as the easiest trap in the batch.

You open the scenario, you see F-101: high severity, open status. That's two out of three
conditions for counting met right there. My first instinct was exit 1, `block`.

But before I wrote anything down I went back and checked the fingerprints. The baseline
`rel-4.11-android` lists `[fp-and-01, fp-and-02]`. F-101's fingerprint is `fp-and-01` —
it's in the baseline. Excluded. Doesn't count. F-102 and F-103 are both below the high
threshold. So the counted findings total is zero, the CLI exits 0, and the label is `pass`.

That's a really important thing to internalise: a finding being high and open doesn't
automatically mean it blocks. If the security team already reviewed it, accepted it in the
last release, and Lina recorded the scan ID — it's in the baseline and it's gone. That's
exactly what Imane asked for in R4. The `--baseline` flag is what makes this work.

After catching that on S01, I made a point of going finding by finding on every scenario
rather than just scanning for the highest severity. It takes longer but you don't get
surprised by S06 where there are five findings and zero of them count — for five completely
different reasons.

