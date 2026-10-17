# Integration Design — Lantern × Kestrel Pay

**Prepared by:** Pre-Sales Engineer, Lantern  
**Date:** 2026-10-19  
**Trial tenant:** EU region, 2026-10-19 → 2026-11-02

---

## 1. Scan Coverage by Pipeline

| Pipeline | Target | Artifact | Command | Blocks? |
|---|---|---|---|---|
| Merge Request (internal) | Android debug APK | `app-debug.apk` | `lantern scan mobile --file <apk> --plan mobile-static --wait --fail-on high` | Yes — on new high/critical |
| Merge Request (fork) | — | — | **skip** (no key available) | N/A |
| Nightly | Android release AAB | `app-release.aab` | `lantern scan mobile --file <aab> --plan mobile-full --wait --fail-on high` | No — report only |
| Nightly | iOS ad-hoc IPA | `Kestrel-adhoc.ipa` | `lantern scan mobile --file <ipa> --plan mobile-full --wait --fail-on high` | No — report only |
| Nightly | Staging web + API | `https://staging.kestrel.test` | `lantern scan web --target <url> --auth staging-ci-token --openapi api/openapi.yaml --wait` | No — report only |
| Release | Android release AAB | `app-release.aab` | `lantern scan mobile --file <aab> --plan mobile-full --baseline $LANTERN_BASELINE_ANDROID --wait --fail-on high` | Yes — on new high/critical |
| Release | iOS App Store IPA | `Kestrel-appstore.ipa` | `lantern scan mobile --file <ipa> --plan mobile-full --baseline $LANTERN_BASELINE_IOS --wait --fail-on high` | Yes — static only, DAST skipped by Lantern (App Store encryption) |

> **Note on MR timing:** A `mobile-full` scan takes 20–45 min (P9). The MR pipeline has only 2 minutes of budget remaining (E2). `mobile-static` is used instead to stay within the 15-minute wall-clock limit.

> **Note on nightly web scan:** Staging is reachable only from the internal network (E5). The job must run on `staging-net` runner. Lantern's egress IPs must be added to the staging allowlist — request pending approval from Imane (~5 business days).

---

## 2. Secrets Handling

- The `LANTERN_API_KEY` **must never appear in YAML**. The key hardcoded in the draft pipeline (`lk_live_7f3c9d1e2b4a4c8e9f0a1b2c3d4e5f60`) must be **revoked immediately** and regenerated from the Lantern dashboard (P8).
- The new key is stored as a **masked, protected CI variable** in GitLab project settings (E3).
- Protected variables are available to `main`, `release/*`, `v*` tags, and scheduled pipelines. They are **not injected into fork MR pipelines** — this is why fork MR scans are skipped (E3).

---

## 3. Baseline Lifecycle

- A baseline is a completed Lantern scan used as a reference. Only findings whose fingerprint is **not** in the baseline count toward exit code 1 (P7).
- Current baselines: `rel-4.11-android` and `rel-4.11-ios` (E4).
- Stored as protected CI variables: `LANTERN_BASELINE_ANDROID` and `LANTERN_BASELINE_IOS`.
- **After each release:** Lina (release manager) updates both variables to the new scan IDs recorded in the Lantern dashboard, then documents them in Jira project KPAY (E4).

---

## 4. Exit Code Policy

| Exit code | Meaning | Gate label |
|---|---|---|
| `0` | Completed, no counted finding at or above threshold | `pass` (release) / `report` (nightly) |
| `1` | Completed, at least one counted finding at or above threshold | `block` (release) / `report` (nightly) |
| `2` | Scan error or `--wait` timed out after 60 min | **`error`** — never treated as pass |
| `3` | Config/auth error before submission (bad key, missing file, unknown baseline) | **`error`** — never treated as pass |

Exit codes 2 and 3 must **never** silently pass the pipeline. If the release gate exits 2 or 3, the release may proceed only after a successful rerun or a documented manual approval by Imane (E4).

---

## 5. Requests R1–R8

| # | Request | Status | Reason / Alternative |
|---|---|---|---|
| R1 | Block MR on high/critical (mobile) | ⚠️ Partly supported | MR budget is 2 min; `mobile-full` takes 20–45 min. MR uses `mobile-static` with `--fail-on high`. Full dynamic coverage is in nightly and release gates. |
| R2 | SAST scan of `web/` and `api/` source code | ❌ Not supported | Lantern has no source-code analysis for web/API (P2). Recommend adding Semgrep or SonarQube as a separate CI step. |
| R3 | Confirm GraphQL testing before signing | ❌ Not supported | Lantern scans GraphQL as generic HTTP only; there is no GraphQL-specific testing and no roadmap date (P2, P11). |
| R4 | Release blocks only on new high/critical | ✅ Supported | `--baseline <scan_id>` excludes known findings from the count (P7). Implemented in the release gate. |
| R5 | Full dynamic testing of the App Store IPA | ❌ Not supported | App Store IPAs are encrypted; Lantern performs static analysis only and skips DAST automatically (P1). Use the nightly ad-hoc IPA for full dynamic coverage. |
| R6 | Automatic ServiceNow ticket creation | ❌ Not supported | No ServiceNow integration exists; it is marked "exploring" with no committed date (P10, P11). Alternative: Jira Cloud two-way sync is available; security ops can mirror to ServiceNow manually. |
| R7 | SARIF artifact for every release | ✅ Supported | `lantern export --scan-id <id> --format sarif --out results.sarif` after the gate, stored as a GitLab artifact (P10). |
| R8 | No silent pass or silent fail | ✅ Supported | Exit codes 2 and 3 are always `error`. `|| true` removed from all security jobs. |

---

## 6. Dependencies — Actions Required from Kestrel

| Action | Owner | Deadline |
|---|---|---|
| Revoke the hardcoded API key in the draft pipeline | Rafa | Immediately |
| Create new `LANTERN_API_KEY` as a masked, protected CI variable | Rafa | Before first run |
| Create `LANTERN_BASELINE_ANDROID` and `LANTERN_BASELINE_IOS` CI variables with current baseline IDs | Rafa | Before first release gate |
| Submit allowlist request for Lantern egress IPs to reach `staging.kestrel.test` | Imane | Immediately (5-day lead time) |
| Ensure `ci-scanner` service account token is valid and configured in `staging-ci-token` auth profile | Imane | Before nightly web scan |
| Update baseline CI variables after each release and record scan IDs in Jira KPAY | Lina | After each release |
