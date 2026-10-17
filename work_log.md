# Work Log & AI-Use Note

**Candidate:** Pre-Sales Engineer applicant  
**Exercise date:** 2026-10-19  
**Time used:** Within the 24-hour window

---

## Prioritization

I started by reading all input files in one pass — environment facts, product facts, prospect
requests, the draft pipeline, and all nine scenario files — before writing anything. The goal
was to map every constraint before making design decisions, because getting the exit-code
policy or the baseline logic wrong early would break the scenario analysis later.

I then tackled the deliverables in order: integration design first (establishes the ground
rules everything else references), then the pipeline fix (applies those rules to real YAML),
then the decision table and scenarios (validates the rules against concrete cases), and
finally the prospect message (distils everything into a client-facing summary).

I prioritised accuracy over speed — specifically making sure the finding count logic (P6, P7)
was applied correctly for each scenario before assigning a label.

---

## One Obstacle and Response

**Obstacle:** S05 (nightly web scan) initially looked like it should produce exit 2 (target
unreachable) rather than exit 3. The staging network is blocked (E5), and I initially focused
on that as the failure cause.

**Response:** Re-reading P8 and the scenario carefully, I noticed `api_key_valid: false` —
the key from 2026-10-16 is already revoked. The CLI checks key validity before attempting
any network connection (P5: exit 3 = config/auth error before submission). The correct exit
code is 3, not 2, and the root cause is the revoked key — not the network block. The network
block is a secondary problem that would surface after the key is fixed. This distinction
matters because the remediation paths are different.

---

## One Validation and Refinement

During the scenario analysis, I initially wrote S01 as `pass` based on a quick read, then
went back to verify each finding individually against the baseline fingerprints and severity
threshold. F-101 is high and open — it looks like it should block — but its fingerprint
`fp-and-01` is listed in the `rel-4.11-android` baseline, so it is excluded by baseline (P7).
Zero counted findings → exit 0 → `pass`. This kind of per-finding verification is essential;
a headline read of the findings list without checking fingerprints would produce the wrong label.

---

## Limits

- The revised pipeline uses a shell exit-code handler (`EXIT=$?`) in nightly jobs to
  downgrade exit 1 to exit 0 with a log message. This pattern works in bash but was not
  tested against a real GitLab runner. A real deployment should validate this behaviour.

- S07 shows that a 70-minute scan will always timeout with the current `--wait` approach.
  A more robust solution would use `--wait` without a blocking gate and poll the scan result
  separately — but this requires a more complex pipeline pattern not covered in the trial scope.

- The SARIF export in the release pipeline captures the scan ID in a variable
  (`LANTERN_SCAN_ID_ANDROID`). The exact mechanism for extracting this from the CLI JSON
  stdout was noted as a comment but not fully scripted, as no programming was required.

- GraphQL coverage and ServiceNow integration are gaps that cannot be addressed with Lantern
  alone during the trial period.

---

## Next Step

If I had more time, I would run the optional mock (`lantern_mock.py`) against all nine
scenarios to cross-check my manual exit-code calculations, and add the commands used to
this log. I would also draft the optional trial success checklist mentioned in the README —
a one-page checklist for Lina and Imane covering the pre-flight actions, the first nightly
run verification, and the baseline update procedure post-release.

---

## AI-Use Note

**Tool used:** Kiro (Claude-based AI assistant in the IDE)

**How it was used:** Kiro was used throughout — to draft all five deliverables, structure
the decision table, and write the revised pipeline YAML.

**One output accepted:** The finding-by-finding analysis tables for each scenario (e.g. the
column layout showing severity / status / fingerprint / in baseline / counts). This format
was suggested by Kiro and I accepted it because it makes the reasoning transparent and
auditable — a reviewer can follow exactly why each finding was included or excluded without
needing to re-read the product facts.

**One output corrected:** In the initial draft of S03 (nightly Android), Kiro described the
nightly job as "not using `--baseline`" without explaining why. I refined this to clarify
that nightly intentionally omits `--baseline` because its purpose is full visibility, not
gated comparison — and that the exit-code handler in the revised pipeline is what prevents
exit 1 from blocking the nightly build. The distinction matters for the decision table.

**One output rejected:** An early draft of the prospect message used bold section headers
(`**What Lantern will do:**`, `**What Lantern will not do:**`). I rejected this format
because it reads like a formal report rather than a human email. The final version uses
flowing paragraphs that sound like how a Pre-Sales Engineer actually talks to a prospect.

---

*No prompt histories or account access are included in this submission.*
