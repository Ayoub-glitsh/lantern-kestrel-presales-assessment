# Pipeline Change List — Kestrel Pay Draft → Revised

**File corrected:** `inputs/current.gitlab-ci.yml` → `pipeline_revised.gitlab-ci.yml`  
**Reviewed by:** Pre-Sales Engineer, Lantern — 2026-10-19  

Every change below references the fact ID(s) that justify it. Facts come from
`inputs/environment.md` (E1–E9), `inputs/product.md` (P1–P12), and `inputs/requests.md` (R1–R8).

---

## B1 — API key hardcoded in YAML variables

**Original:**
```yaml
variables:
  LANTERN_API_KEY: "lk_live_7f3c9d1e2b4a4c8e9f0a1b2c3d4e5f60"
```

**Fix:** The entire `LANTERN_API_KEY` line is removed from the YAML file.  
The key must be **revoked immediately** from the Lantern dashboard, a new key generated,
and stored as a **masked + protected CI variable** in GitLab project settings.

**Why it matters:** The key was visible to anyone with repository read access, appeared in
Git history, and would have been printed in CI logs. Kestrel's own policy requires production
API keys to be stored only as masked, protected CI variables.

**Ref:** E3 (secrets policy), P8 (CLI reads key from env var; revoked key gives exit 3)

---

## B2 — MR scan used `mobile-full` — exceeds time budget

**Original:**
```yaml
lantern-mr-android:
  script:
    - lantern scan mobile ... --plan mobile-full --wait --fail-on high
```

**Fix:** Changed `--plan mobile-full` to `--plan mobile-static`.

**Why it matters:** The MR pipeline has only 2 minutes of budget remaining after lint (2 min),
unit tests (5 min), and the debug build (6 min). A `mobile-full` scan takes 20–45 minutes and
would cause every MR pipeline to time out, making the gate useless. `mobile-static` performs
static analysis only and fits within the budget while still catching high and critical findings.

**Ref:** E2 (15-minute MR wall-clock budget), P9 (mobile scan durations 20–45 min)

---

## B3 — `|| true` silenced scan errors on nightly jobs

**Original:**
```yaml
lantern-nightly-mobile:
  script:
    - lantern scan mobile ... --plan mobile-full --wait --fail-on high || true
    - lantern scan mobile ... --plan mobile-full --wait --fail-on high || true

lantern-nightly-web:
  script:
    - lantern scan web ... || true
```

**Fix:** Removed all `|| true` constructs. Each nightly job now uses an explicit exit-code
handler: exit 1 (findings) is downgraded to exit 0 with an informational message, because
nightly is a reporting run and must not block the pipeline on findings. Exit 2 (scan error)
and exit 3 (config/auth error) are passed through unchanged, which fails the job and alerts
the team.

**Why it matters:** `|| true` forces every command to exit 0 regardless of the real exit code.
If the API key is revoked (exit 3) or a scan times out (exit 2), the job silently turns green.
Rafa's requirement R8 explicitly forbids this: a broken scanner must be visible, and it must
never quietly turn the pipeline green for the wrong reason.

**Ref:** R8 (no silent pass/fail), P5 (exit codes 0/1/2/3 definitions)

---

## B4 — Nightly web scan used `staging-qa-user` — MFA blocks login

**Original:**
```yaml
lantern-nightly-web:
  script:
    - lantern scan web --target https://staging.kestrel.test --auth staging-qa-user ...
```

**Fix:** Changed `--auth staging-qa-user` to `--auth staging-ci-token`.

**Why it matters:** The `staging-qa-user` auth profile uses a recorded login of `qa-auto`.
Since 2026-10-01, `qa-auto` has MFA enforced. Lantern's recorded login mechanism cannot
complete MFA challenges — the authentication would fail at scan time (exit 3). The correct
profile is `staging-ci-token`, which uses a static bearer token for the `ci-scanner` service
account — no MFA involved.

**Ref:** E6 (MFA enforced on qa-auto since 2026-10-01), P2 (recorded login cannot complete MFA)

---

## B5 — Nightly web scan ran on `saas-linux` — cannot reach staging

**Original:**
```yaml
lantern-nightly-web:
  # no tags — inherits default: saas-linux
  script:
    - lantern scan web --target https://staging.kestrel.test ...
```

**Fix:** Added `tags: [staging-net]` to `lantern-nightly-web`.

**Why it matters:** `staging.kestrel.test` is reachable only from the internal network.
`saas-linux` is a shared runner with no internal network access. The scan submission would
fail with a connection error. The `staging-net` self-hosted runner sits on the internal
network and can reach both staging and the Lantern SaaS API via its proxy.

Note: even with the correct runner, the web scan will exit 3 (target unreachable from
Lantern's egress IPs) until Imane files the allowlist request for Lantern's IP ranges (~5
business days, action item A6).

**Ref:** E5 (staging reachable only from internal network), E7 (runner tags), P3 (Lantern scans from its own egress IPs)

---

## B6 — Release gate had `allow_failure: true` — security block was bypassed

**Original:**
```yaml
lantern-release-gate:
  allow_failure: true
  script:
    - lantern scan mobile ...
```

**Fix:** Removed `allow_failure: true` from both `lantern-release-android` and
`lantern-release-ios`.

**Why it matters:** `allow_failure: true` tells GitLab to mark the job as a warning and
continue the pipeline even if the job fails. This means a release could reach the manual
`publish` job even after a blocking security finding (exit 1) or a scan error (exit 2/3).
The release gate must fail the pipeline on any non-zero exit code so the `publish` job
remains locked.

**Ref:** E4 (release gate must block on new high/critical findings), R8 (no silent pass/fail)

---

## B7 — Release gate used `--fail-on medium` — contradicts release policy

**Original:**
```yaml
lantern-release-gate:
  script:
    - lantern scan mobile ... --fail-on medium
    - lantern scan mobile ... --fail-on medium
```

**Fix:** Changed both instances from `--fail-on medium` to `--fail-on high`.

**Why it matters:** Kestrel's release policy (E4) states that a release is blocked only by
new **high or critical** findings. Setting `--fail-on medium` would block releases on medium
findings that are not covered by the policy, creating unnecessary noise and blocking valid
releases. The threshold must match the policy exactly.

**Ref:** E4 (release blocked only by new high or critical), P5 (--fail-on sets the threshold for exit code 1)

---

## B8 — Release gate had no `--baseline` flag — all known findings blocked

**Original:**
```yaml
lantern-release-gate:
  script:
    - lantern scan mobile ... --plan mobile-full --wait --fail-on medium
    - lantern scan mobile ... --plan mobile-full --wait --fail-on medium
```

**Fix:** Added `--baseline $LANTERN_BASELINE_ANDROID` to the Android scan and
`--baseline $LANTERN_BASELINE_IOS` to the iOS scan.

These variables are stored as protected CI variables in GitLab and hold the scan IDs of
the last accepted release:
- `LANTERN_BASELINE_ANDROID` = `rel-4.11-android`
- `LANTERN_BASELINE_IOS` = `rel-4.11-ios`

Lina (release manager) must update both variables after each release.

**Why it matters:** Without a baseline, every finding in the current scan — including
findings already tracked and accepted in Jira KPAY — counts toward exit code 1 and blocks
the release. The entire point of Imane's request R4 is to block only on genuinely new
findings. The `--baseline` flag implements this by excluding findings whose fingerprint
already exists in the reference scan.

**Ref:** E4 (block only on new findings), R4 (known findings tracked in Jira must not block), P7 (baseline mechanism)

---

## B9 — No handling for scan timeout (exit 2) on release

**Original:** No mention of exit 2 behaviour in the release job.

**Fix:** The release jobs do not use `|| true` and do not suppress exit 2. If a scan
exceeds the 60-minute `--wait` cap (possible for large binaries, as seen in S07 where
the scan takes 70 minutes), the CLI exits 2, the job fails, and the `publish` job is
locked. The release may then proceed only after a successful rerun or a documented
manual approval by Imane (E4).

This is documented in comments within the pipeline file and in the integration design (§3.3).

**Ref:** E4 (manual approval path), P4 (--wait blocks for at most 60 minutes), P5 (exit 2 on timeout)

---

## B10 — Fork MRs would fail with exit 3 instead of being skipped

**Original:**
```yaml
lantern-mr-android:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
  script:
    - lantern scan mobile ...
```

**Fix:** Added a rule to skip the scan job when the MR source project differs from the
target project (i.e. a fork):

```yaml
rules:
  - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID'
  - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID != $CI_PROJECT_ID'
    when: never
```

**Why it matters:** GitLab does not inject protected variables into pipelines triggered from
forks (E3). If the scan job runs without a key, the CLI exits 3 (auth error before submission).
This would block every external contributor's MR with a confusing infrastructure error rather
than a security finding. The correct behaviour is to skip the scan silently, which is what
the revised rules implement.

**Ref:** E3 (protected variables not available in fork pipelines), P8 (missing key → exit 3)

---

## B11 — No SARIF export after release scan

**Original:** No `lantern export` command in the release gate job.

**Fix:** Added `after_script` blocks to both `lantern-release-android` and
`lantern-release-ios` that call `lantern export --format sarif` and store the output as a
GitLab pipeline artifact with `expire_in: 1 year`.

**Why it matters:** Rafa's request R7 requires a SARIF file for every release so auditors
can see what was checked. Without the export step, scan results exist only in the Lantern
dashboard and are not attached to the GitLab pipeline for audit retrieval.

**Ref:** R7 (SARIF artifact per release), P10 (lantern export --format sarif produces SARIF 2.1.0)

---

## B12 — Nightly iOS scan had no `macos` runner tag

**Original:**
```yaml
lantern-nightly-mobile:
  # no tags — inherits default: saas-linux
  script:
    - lantern scan mobile --file ios/build/Kestrel-adhoc.ipa ...
```

**Fix:** Split `lantern-nightly-mobile` into two separate jobs — `lantern-nightly-android`
(runs on `saas-linux`, the default) and `lantern-nightly-ios` (runs on `macos`).

**Why it matters:** The iOS IPA artifact is produced by `build-ios-adhoc` which runs on the
`macos` runner. GitLab artifacts are passed between jobs that share a runner tag. If the
scan job runs on `saas-linux`, it cannot access the IPA file produced on `macos` and the
scan would fail with a file-not-found error (exit 3).

**Ref:** E1 (iOS builds on macos runner), E7 (runner tags), P8 (missing file → exit 3)

---

## Summary Table

| ID | Location in draft | Issue | Fix applied |
|---|---|---|---|
| B1 | `variables` block | API key hardcoded in YAML | Removed; key moved to protected CI variable |
| B2 | `lantern-mr-android` | `--plan mobile-full` exceeds MR time budget | Changed to `--plan mobile-static` |
| B3 | `lantern-nightly-mobile`, `lantern-nightly-web` | `\|\| true` silences exit codes 2 and 3 | Replaced with explicit exit-code handler |
| B4 | `lantern-nightly-web` | `--auth staging-qa-user` fails due to MFA | Changed to `--auth staging-ci-token` |
| B5 | `lantern-nightly-web` | No runner tag — runs on saas-linux, cannot reach staging | Added `tags: [staging-net]` |
| B6 | `lantern-release-gate` | `allow_failure: true` bypasses the security block | Removed `allow_failure: true` |
| B7 | `lantern-release-gate` | `--fail-on medium` contradicts release policy | Changed to `--fail-on high` |
| B8 | `lantern-release-gate` | No `--baseline` — known findings block release | Added `--baseline $LANTERN_BASELINE_*` |
| B9 | `lantern-release-gate` | Exit 2 (timeout) not handled explicitly | Documented; exit 2 fails job → rerun or Imane approval |
| B10 | `lantern-mr-android` | Fork MRs would exit 3 instead of being skipped | Added fork detection rule with `when: never` |
| B11 | `lantern-release-gate` | No SARIF export | Added `lantern export` in `after_script` with 1-year artifact |
| B12 | `lantern-nightly-mobile` | iOS scan had no `macos` tag — file not accessible | Split into two jobs; iOS job gets `tags: [macos]` |
