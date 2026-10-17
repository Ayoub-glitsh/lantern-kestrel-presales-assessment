# Gate Decision Table — Batch 2 Results (S07–S09)

**Prepared by:** Pre-Sales Engineer, Lantern — 2026-10-19  
**Reference table:** `gate_decision_table.md` (Livrable 3)  
**Scenario snapshot:** 2026-10-19 09:00 UTC

---

## Table of Contents

1. [Table Updates After Batch 2](#1-table-updates-after-batch-2)
2. [Batch 2 Results](#2-batch-2-results)
3. [Combined Summary — All 9 Scenarios](#3-combined-summary--all-9-scenarios)

---

## 1. Table Updates After Batch 2

After applying the original table to S07, S08, and S09, two cases required clarification.
The core logic did not change — both cases already resolve to `error` under row 3 and row 2 of
the original table — but the remediation paths needed to be made explicit.

---

### Update U1 — Exit 2 on release: scan timeout procedure

**Triggered by:** S07 (scan duration 70 min > 60 min `--wait` cap)

**Original table row 3:**
> any pipeline, key valid, exit 2 → `error` — scan error or --wait timeout

**Added clarification:**
When exit 2 occurs on a **release** pipeline specifically because of a scan timeout (not a
server-side error), the scan is still running server-side and results will appear in the
Lantern dashboard (P4). The `publish` job is locked. Two remediation paths exist:

- **Path A — Rerun:** wait for the scan to complete server-side, then re-trigger the release
  pipeline. If the scan now completes within 60 min (e.g. the binary was unusually large that
  day), it exits 0 or 1 normally.
- **Path B — Manual approval:** Imane reviews the in-progress or completed scan result in the
  Lantern dashboard and provides documented manual approval to proceed (E4).

Neither path treats exit 2 as a pass. The pipeline never turns green from a timeout alone.

**Ref:** E4 (manual approval path), P4 (--wait blocks up to 60 min; scan continues server-side), P5 (exit 2 definition)

---

### Update U2 — Exit 3 on release: invalid baseline ID

**Triggered by:** S08 (baseline variable `LANTERN_BASELINE_IOS` = `rel-4.12-ios` but that
scan does not yet exist in the tenant — it is a future release ID set prematurely)

**Original table row 2:**
> any pipeline, key valid, exit 3 → `error` — auth/config error before submission

**Added clarification:**
When exit 3 occurs because the **baseline scan ID is not found** in the tenant (P7), the
root cause is a configuration error by the person who set the CI variable — not a key
problem. The fix is:

1. Identify the correct existing baseline scan ID in the Lantern dashboard
2. Update the `LANTERN_BASELINE_ANDROID` or `LANTERN_BASELINE_IOS` CI variable to the
   correct value
3. Re-trigger the release pipeline

This is distinct from a revoked key (also exit 3) and must be diagnosed from the CLI error
output. The `publish` job remains locked until the pipeline reruns successfully.

**Ref:** P7 (baseline must be a completed scan in the same tenant; otherwise CLI exits 3), P5 (exit 3 definition)

---

### Updated Decision Table (v2)

The table structure is unchanged. Two footnotes are added to row 2 and row 3.

| Row | Pipeline type | Fork | Key valid | Exit code | Counted findings | Label | Reason |
|---|---|---|---|---|---|---|---|
| 1 | any | ✅ yes | — | — | — | `skip` | Fork MR — key not injected by GitLab (E3) |
| 2 | any | no | ❌ no / invalid | 3 | — | `error` | Auth/config error before submission — see note ① |
| 3 | any | no | ✅ yes | 2 | — | `error` | Scan error or --wait timeout — see note ② |
| 4 | nightly | no | ✅ yes | 0 or 1 | any | `report` | Nightly is monitoring only — never blocks |
| 5 | release / MR | no | ✅ yes | 0 | 0 | `pass` | Scan completed, no new finding at or above threshold |
| 6 | release / MR | no | ✅ yes | 1 | ≥ 1 | `block` | New high/critical finding — pipeline must stop |

**① Exit 3 remediation:** Check CLI error output. If cause is revoked key → action A1/A2
(revoke + regenerate). If cause is baseline not found → correct the CI variable to an
existing scan ID and rerun. Never treat as pass.

**② Exit 2 remediation (release):** Scan may still be running server-side. Wait for
completion in Lantern dashboard, then either rerun the pipeline (Path A) or obtain Imane's
documented manual approval (Path B, E4). Never treat as pass.

---

## 2. Batch 2 Results

---

### S07 — Release 4.13.0: Android gate, large bundle (slow scan)

**Context:** Release pipeline, tag `v4.13.0` on `release/4.13`, not a fork, runner `saas-linux`.  
Key: set and valid. Baseline: `rel-4.11-android` → fingerprints `[fp-and-01, fp-and-02]`.  
Scan duration: **70 minutes** — exceeds the 60-minute `--wait` cap (P4).

**Command my pipeline runs:**
```bash
lantern scan mobile \
  --file android/app/build/outputs/bundle/release/app-release.aab \
  --plan mobile-full \
  --baseline rel-4.11-android \
  --wait \
  --fail-on high
```

**What happens:** The scan is submitted successfully. After 60 minutes, `--wait` stops
blocking and the CLI exits 2 — the scan is still running server-side (P4, P5). The findings
(including F-701, a new high) have not yet been evaluated at the time the CLI exits.

**Finding analysis:** Not evaluated at exit time — scan was still in progress.

| Finding | Severity | Status | Fingerprint | Note |
|---|---|---|---|---|
| F-701 — Intent redirection in deep link handler | high | open | `fp-and-70` | Would count if scan had completed — new, open, above threshold |

**Counted findings at CLI exit: N/A** (timeout before completion)

**Exit code: 2** — `--wait` timed out after 60 minutes (P4, P5)

**Label: `error`**

**Reason:** Scan timeout — `--wait` exited after 60 min, scan still running server-side (P4).
Release `publish` locked. Remediate via Path A (rerun after scan completes) or Path B
(Imane manual approval after reviewing dashboard result, E4). Exit 2 never treated as pass
(update U1).

---

### S08 — Release 4.13.0: iOS gate, wrong baseline ID

**Context:** Release pipeline, tag `v4.13.0` on `release/4.13`, not a fork, runner `macos`.  
Key: set and valid. Baseline variable `LANTERN_BASELINE_IOS` = `rel-4.12-ios`.  
iOS signing: `app_store` → DAST skipped automatically (P1).

**Available baselines in tenant:** only `rel-4.11-ios` → fingerprints `[fp-ios-01]`.  
`rel-4.12-ios` **does not exist** in the tenant — it was set prematurely (future release ID).

**Command my pipeline runs:**
```bash
lantern scan mobile \
  --file ios/build/Kestrel-appstore.ipa \
  --plan mobile-full \
  --baseline rel-4.12-ios \
  --wait \
  --fail-on high
```

**What happens:** The CLI attempts to resolve baseline `rel-4.12-ios` in the tenant before
submitting the scan. The baseline is not found. The CLI exits 3 immediately — the scan is
never submitted (P7, P5).

**Finding analysis:** Not evaluated — scan never submitted.

| Finding | Severity | Status | Fingerprint | Note |
|---|---|---|---|---|
| F-801 — Pasteboard used for one-time code | low | open | `fp-ios-80` | Would not count even if scan ran — below threshold (low < high) |

**Counted findings: N/A** (scan not submitted)

**Exit code: 3** — baseline `rel-4.12-ios` not found in tenant (P7, P5)

**Label: `error`**

**Reason:** Baseline ID `rel-4.12-ios` does not exist in the Lantern tenant — CLI exits 3
before scan submission (P7). Root cause: `LANTERN_BASELINE_IOS` CI variable was set to a
future release ID that has not been created yet. Fix: update `LANTERN_BASELINE_IOS` to
`rel-4.11-ios` (the last existing baseline) and rerun. See update U2 for remediation
procedure.

---

### S09 — Release 4.13.1: Android gate, one known + one new high finding

**Context:** Release pipeline, tag `v4.13.1` on `release/4.13`, not a fork, runner `saas-linux`.  
Key: set and valid. Baseline: `rel-4.11-android` → fingerprints `[fp-and-01, fp-and-02]`.  
Scan duration: 39 minutes — completes within `--wait` 60-minute cap.

**Command my pipeline runs:**
```bash
lantern scan mobile \
  --file android/app/build/outputs/bundle/release/app-release.aab \
  --plan mobile-full \
  --baseline rel-4.11-android \
  --wait \
  --fail-on high
```

**Finding analysis:**

| Finding | Severity | Status | Fingerprint | In baseline? | Counts? | Reason |
|---|---|---|---|---|---|---|
| F-901 — Exported activity without permission check | high | open | `fp-and-01` | ✅ yes | ❌ | Excluded by baseline (P7) |
| F-902 — Token stored in shared preferences without encryption | high | open | `fp-and-90` | ❌ no | ✅ **counts** | New, open, severity high ≥ threshold (P5, P6) |
| F-903 — Legacy payment SDK with known vulnerability | critical | risk_accepted | `fp-and-91` | ❌ no | ❌ | Status `risk_accepted` never counts (P6) |

**Counted findings: 1** (F-902)

**Exit code: 1** — scan completed, 1 counted finding at or above threshold (P5)

**Label: `block`**

**Reason:** New high finding F-902 ("Token stored in shared preferences without encryption")
is open, not in the baseline, and at severity high ≥ threshold. F-901 is excluded by
baseline, F-903 is risk-accepted. One genuine new risk detected — release gate failed,
`publish` locked until F-902 is remediated or manually approved by Imane (E4).

---

## 3. Combined Summary — All 9 Scenarios

| # | Scenario | Pipeline | Exit code | Counted findings | Label |
|---|---|---|---|---|---|
| S01 | Release 4.12.0 — Android | release | 0 | 0 (F-101 in baseline) | `pass` |
| S02 | Release 4.12.0 — iOS | release | 1 | 1 (F-201 new critical) | `block` |
| S03 | Nightly — Android | nightly | 1 → 0 | 1 (F-301, downgraded) | `report` |
| S04 | Fork MR | merge_request | N/A | N/A | `skip` |
| S05 | Nightly — web/API | nightly | 3 | N/A (key revoked) | `error` |
| S06 | Release 4.12.1 hotfix — Android | release | 0 | 0 (all excluded) | `pass` |
| S07 | Release 4.13.0 — Android slow scan | release | 2 | N/A (timeout) | `error` |
| S08 | Release 4.13.0 — iOS wrong baseline | release | 3 | N/A (baseline not found) | `error` |
| S09 | Release 4.13.1 — Android new vs known | release | 1 | 1 (F-902 new high) | `block` |
