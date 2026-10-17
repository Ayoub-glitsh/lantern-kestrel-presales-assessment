# Lantern × Kestrel Pay — CI/CD Integration Design

| | |
|---|---|
| **Document type** | Pre-Sales Integration Design |
| **Prepared by** | Pre-Sales Engineer, Lantern |
| **Prospect** | Kestrel Pay (fictional) |
| **Trial period** | 2026-10-19 → 2026-11-02 (EU tenant) |
| **Contacts** | Rafa (Platform Lead), Imane (Security Lead), Lina (Release Manager) |
| **Status** | Draft — for trial review |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Scan Coverage by Pipeline](#3-scan-coverage-by-pipeline)
4. [Secrets Handling](#4-secrets-handling)
5. [Baseline Lifecycle](#5-baseline-lifecycle)
6. [Exit Code Policy](#6-exit-code-policy)
7. [Prospect Requests R1–R8](#7-prospect-requests-r1r8)
8. [Dependencies & Action Items](#8-dependencies--action-items)

---

## 1. Executive Summary

Kestrel Pay operates a GitLab monorepo with Android, iOS, web, and API components. This document defines how Lantern's security scanning integrates into each pipeline type — merge request, nightly, and release — while respecting Kestrel's time budgets, secrets policy, and release gate requirements.

**Key design decisions at a glance:**

- 🔒 **Release gate** blocks on new high/critical findings only, using baseline comparison
- ⚡ **MR gate** uses static-only scan to fit within the 2-minute remaining budget
- 📊 **Nightly pipeline** runs full scans (static + dynamic) and reports without blocking
- 🚫 **Fork MRs** skip scanning — no API key is available by design (GitLab protected variables)
- ❌ Exit codes `2` and `3` are always treated as `error` — never as a pass

---

## 2. Architecture Overview

### 2.1 How Lantern Works in a Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitLab Runner                            │
│                                                                 │
│   pipeline job                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │  lantern scan mobile --file app.aab --plan mobile-full   │  │
│   │                 --baseline $BASELINE_ID                  │  │
│   │                 --wait --fail-on high                    │  │
│   └──────────────────────────┬───────────────────────────────┘  │
│                              │  uploads artifact / URL          │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │   Lantern SaaS (EU)   │
                   │                       │
                   │  ┌─────────────────┐  │
                   │  │  Scan Engine    │  │
                   │  │  (static+dast)  │  │
                   │  └────────┬────────┘  │
                   │           │           │
                   │  ┌────────▼────────┐  │
                   │  │  Baseline diff  │  │
                   │  │  & threshold    │  │
                   │  └────────┬────────┘  │
                   └───────────┼───────────┘
                               │  JSON result + exit code
                               ▼
                   ┌───────────────────────┐
                   │   Gate Decision       │
                   │   pass / block /      │
                   │   report / error /    │
                   │   skip                │
                   └───────────────────────┘
```

> **How to read this diagram:** The Lantern CLI runs inside the GitLab runner as part of a pipeline job. It does **not** perform the scan locally — it simply packages the binary file (APK, AAB, IPA) or the target URL and sends it to the Lantern SaaS platform hosted in the EU region. The SaaS engine then runs the actual static and/or dynamic analysis, compares results against the baseline scan (if provided), applies the severity threshold, and returns a JSON result object plus an exit code. The runner receives that exit code and decides whether to pass, block, or flag an error. The key implication: **the runner needs internet access to reach Lantern, but Lantern's scanners need to reach your web target directly** — which is why `staging.kestrel.test` requires an allowlist (see §2.3).

---

### 2.2 Pipeline Flow Diagram

```
  Git Event
      │
      ├─── Merge Request ──────────────────────────────────────────────┐
      │         │                                                       │
      │    Fork MR?                                                     │
      │    ├── YES → [SKIP] No key available (E3)                      │
      │    └── NO  → build android debug APK                           │
      │                   └── lantern scan mobile (static only)        │
      │                              └── fail-on high → [BLOCK / PASS] │
      │                                                                 │
      ├─── Nightly (02:00 UTC on main) ───────────────────────────────┐│
      │         │                                                      ││
      │    build android AAB ──► lantern scan mobile (full)           ││
      │    build iOS ad-hoc  ──► lantern scan mobile (full)           ││
      │    staging available?──► lantern scan web + API               ││
      │         └── all results → [REPORT] pipeline continues         ││
      │                                                                ││
      └─── Release (v* tag on release/*) ────────────────────────────┐││
                │                                                     │││
           build android AAB ──► lantern scan mobile (full)          │││
                                      + --baseline $ANDROID_BASELINE  │││
           build iOS appstore ──► lantern scan mobile (full)         │││
                                      + --baseline $IOS_BASELINE      │││
                │                                                     │││
           exit 0 → [PASS] ──► manual publish job unlocked           │││
           exit 1 → [BLOCK] ──► new high/critical found              │││
           exit 2 → [ERROR] ──► timeout, rerun or Imane approval     │││
           exit 3 → [ERROR] ──► config/auth issue, fix & rerun       │││
```

> **How to read this diagram:** Every Git event (a push, a tag, a schedule) triggers one of three pipeline types. A **merge request** runs a fast static scan and blocks the merge if a new high/critical finding is detected — fork MRs are skipped entirely because GitLab does not expose protected variables to external contributor pipelines (E3). The **nightly** pipeline is the most thorough: it runs full static + dynamic scans on Android, iOS, and the staging web/API — but it never blocks; it records findings for the team to review. The **release** pipeline is the hard gate: it compares every finding against the last accepted baseline, and only *new* high or critical findings cause a block. Exit codes 2 and 3 (technical errors) always surface as `error` and never silently pass a broken scan through.

---

### 2.3 Runner & Network Topology

```
                        ┌──────────────────────────────────────┐
                        │           GitLab Runners             │
                        │                                      │
  Internet egress ───►  │  saas-linux   (shared, Linux)        │ ──► Lantern SaaS EU
  Internet egress ───►  │  staging-net  (self-hosted, Linux)   │ ──► Lantern SaaS EU
  No internet   ─────►  │  macos        (iOS builds only)      │ ──► Lantern SaaS EU
                        └──────────────────┬───────────────────┘
                                           │
                        ┌──────────────────▼───────────────────┐
                        │        Internal Network              │
                        │                                      │
                        │   staging.kestrel.test               │
                        │   (reachable only from staging-net)  │
                        │                                      │
                        │   ⚠️  Lantern egress IPs NOT yet     │
                        │   allowlisted — request pending       │
                        └──────────────────────────────────────┘
```

> **How to read this diagram:** Kestrel runs three types of runners. `saas-linux` is a shared GitLab runner with direct internet access — it handles Android builds and most security scans. `staging-net` is a self-hosted runner sitting inside the internal network, which is the only way to reach `staging.kestrel.test`; it also has internet egress through a proxy so it can still reach the Lantern SaaS API. `macos` is dedicated to iOS builds and has no special network requirements. The critical blocker: Lantern's scan engine connects *from its own cloud infrastructure* to reach `staging.kestrel.test` — so even though `staging-net` can submit the scan, Lantern's egress IPs must be added to the staging firewall allowlist before the web/API scan can actually run. That request has not been filed yet and takes ~5 business days (E5).

---

## 3. Scan Coverage by Pipeline

### 3.1 Merge Request Pipeline

**Time budget:** 15 min total — 13 min already consumed (lint + tests + build). **2 minutes remaining.**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MR Pipeline                                                            │
│                                                                         │
│  lint (2 min) → unit-tests (5 min) → build-android-debug (6 min)       │
│                                              │                          │
│                                   lantern-mr-android                    │
│                                   ┌─────────────────────────────────┐   │
│                                   │ scan mobile                     │   │
│                                   │ --plan mobile-static            │   │
│                                   │ --wait                          │   │
│                                   │ --fail-on high                  │   │
│                                   │                                 │   │
│                                   │ ⚠️  mobile-full NOT used:       │   │
│                                   │ 20-45 min > 2 min budget (E2)  │   │
│                                   └─────────────────────────────────┘   │
│                                                                         │
│  Fork MR → job skipped (no LANTERN_API_KEY available) (E3)             │
└─────────────────────────────────────────────────────────────────────────┘
```

> **How to read this diagram:** By the time the Android debug build finishes, the MR pipeline has already consumed 13 of its 15-minute budget (lint 2 min + unit tests 5 min + build 6 min), leaving only 2 minutes for security scanning. A `mobile-full` scan takes 20–45 minutes (P9) — running it with `--wait` would cause every MR to time out. The solution is `mobile-static`, which performs static analysis only and completes fast enough to fit the budget. Dynamic analysis (DAST) is deferred to the nightly pipeline which has a 5-hour window. For fork MRs (external contributors), GitLab's protected variable policy prevents the `LANTERN_API_KEY` from being injected at all (E3), so the scan job is skipped rather than failing with a confusing auth error.

| Field | Value |
|---|---|
| Artifact | `android/app/build/outputs/apk/debug/app-debug.apk` |
| Plan | `mobile-static` |
| Blocks pipeline | Yes — on new high/critical |
| Fork behavior | `skip` — key not injected (E3) |

**Command:**
```bash
lantern scan mobile \
  --file android/app/build/outputs/apk/debug/app-debug.apk \
  --plan mobile-static \
  --wait \
  --fail-on high
```

---

### 3.2 Nightly Pipeline

**Window:** 02:00–07:00 UTC (5-hour budget). Runs on `main`.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Nightly Pipeline (02:00 UTC)                                           │
│                                                                         │
│  ┌─────────────────────┐   ┌──────────────────────┐                    │
│  │ build-android-       │   │ build-ios-adhoc      │                    │
│  │ release (AAB)        │   │ (ad-hoc IPA)         │                    │
│  └──────────┬──────────┘   └──────────┬───────────┘                    │
│             │                         │                                 │
│  ┌──────────▼──────────┐   ┌──────────▼───────────┐                    │
│  │ lantern scan mobile │   │ lantern scan mobile  │                    │
│  │ --plan mobile-full  │   │ --plan mobile-full   │                    │
│  │ --wait (≤60 min)    │   │ --wait (≤60 min)     │                    │
│  │ --fail-on high      │   │ --fail-on high       │                    │
│  │ → REPORT (no block) │   │ → REPORT (no block)  │                    │
│  └─────────────────────┘   └──────────────────────┘                    │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ lantern-nightly-web (runner: staging-net)                        │   │
│  │ scan web --target https://staging.kestrel.test                   │   │
│  │          --auth staging-ci-token                                 │   │
│  │          --openapi api/openapi.yaml                              │   │
│  │          --wait                                                  │   │
│  │ → REPORT (no block)                                              │   │
│  │                                                                  │   │
│  │ ⚠️  Blocked until Lantern egress IPs allowlisted (E5)           │   │
│  │ ⚠️  Must use staging-ci-token, NOT staging-qa-user (MFA on E6)  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

> **How to read this diagram:** The nightly pipeline runs at 02:00 UTC on the `main` branch and has until 07:00 UTC — a 5-hour window. This allows running `mobile-full` scans (static + dynamic, up to 45 min per target) and the web/API DAST (up to 90 min) in parallel without any time pressure. Crucially, **none of these scans block the pipeline** — findings are recorded in the Lantern dashboard and routed to Jira, but the nightly build is not stopped. This lets the team track trends daily without disrupting the release rhythm. Two important constraints apply to the web scan: (1) it must run on the `staging-net` runner since staging is on the internal network, and (2) it must authenticate using the `staging-ci-token` profile (bearer token for `ci-scanner`) — the `staging-qa-user` profile uses `qa-auto` which has MFA enforced since 2026-10-01 (E6), and Lantern's recorded login cannot complete MFA challenges (P2).

| Job | Target | Plan | Auth | Blocks |
|---|---|---|---|---|
| `lantern-nightly-android` | `app-release.aab` | `mobile-full` | — | No — report |
| `lantern-nightly-ios` | `Kestrel-adhoc.ipa` | `mobile-full` | — | No — report |
| `lantern-nightly-web` | `https://staging.kestrel.test` | DAST + OpenAPI | `staging-ci-token` | No — report |

---

### 3.3 Release Pipeline

**Time budget:** 90 minutes to reach manual `publish` job.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Release Pipeline (v* tag on release/*)                                 │
│                                                                         │
│  build-android-release (AAB)         build-ios-release (App Store IPA) │
│          │                                       │                      │
│  ┌───────▼──────────────────┐   ┌────────────────▼──────────────────┐  │
│  │ lantern scan mobile      │   │ lantern scan mobile               │  │
│  │ --plan mobile-full       │   │ --plan mobile-full                │  │
│  │ --baseline               │   │ --baseline                        │  │
│  │   $LANTERN_BASELINE_     │   │   $LANTERN_BASELINE_IOS           │  │
│  │   ANDROID                │   │                                   │  │
│  │ --wait                   │   │ --wait                            │  │
│  │ --fail-on high           │   │ --fail-on high                    │  │
│  │                          │   │                                   │  │
│  │ ✅ Static + Dynamic      │   │ ✅ Static only                    │  │
│  │                          │   │ ⚠️  DAST skipped —               │  │
│  │                          │   │ App Store IPA encrypted (P1)      │  │
│  └───────────┬──────────────┘   └───────────────────┬───────────────┘  │
│              └─────────────────┬─────────────────────┘                  │
│                                │                                        │
│                     ┌──────────▼──────────┐                             │
│                     │   Gate Decision     │                             │
│                     │                     │                             │
│                     │  exit 0 → PASS      │                             │
│                     │  exit 1 → BLOCK     │                             │
│                     │  exit 2 → ERROR     │                             │
│                     │  exit 3 → ERROR     │                             │
│                     └──────────┬──────────┘                             │
│                                │                                        │
│              ┌─────────────────┴─────────────────┐                     │
│              │                                   │                     │
│     PASS ────►  lantern export (SARIF)           │                     │
│              │  → artifact (30 days) (R7)        │                     │
│              │           │                       │                     │
│              │  manual publish job unlocked      │                     │
│              └───────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────┘
```

> **How to read this diagram:** A release pipeline is triggered when Rafa creates a `v*` tag on a `release/*` branch. Both Android and iOS scans run in parallel, each comparing results against their respective baseline scan from the last accepted release. Only findings whose fingerprint does **not** appear in the baseline are counted — this is how Kestrel's "block only on new" policy (E4, R4) is enforced. The Android AAB gets full static + dynamic analysis. The App Store IPA gets static analysis only because Apple's encryption prevents Lantern from running the dynamic engine (P1) — this is expected behaviour, not an error. If both scans exit 0, the gate passes, a SARIF report is exported for audit purposes (R7), and the manual `publish` job is unlocked for Lina. If either scan exits 1 (new high/critical finding), 2 (timeout), or 3 (config error), the `publish` job remains locked and the release is blocked until remediated or manually approved by Imane (E4).

**Commands:**
```bash
# Android
lantern scan mobile \
  --file android/app/build/outputs/bundle/release/app-release.aab \
  --plan mobile-full \
  --baseline $LANTERN_BASELINE_ANDROID \
  --wait \
  --fail-on high

# iOS (App Store — static only, DAST skipped automatically)
lantern scan mobile \
  --file ios/build/Kestrel-appstore.ipa \
  --plan mobile-full \
  --baseline $LANTERN_BASELINE_IOS \
  --wait \
  --fail-on high

# SARIF export after gate passes
lantern export \
  --scan-id $LANTERN_SCAN_ID \
  --format sarif \
  --out lantern-release.sarif
```

---

## 4. Secrets Handling

### 4.1 Current Problem

```
# ❌ CURRENT DRAFT — CRITICAL SECURITY ISSUE
variables:
  LANTERN_API_KEY: "lk_live_7f3c9d1e2b4a4c8e9f0a1b2c3d4e5f60"
```

> This key is exposed in the repository. **It must be revoked immediately** from the Lantern dashboard and regenerated (P8).

### 4.2 Correct Approach

```
GitLab Project Settings
└── CI/CD
    └── Variables
        ├── LANTERN_API_KEY          [masked] [protected] ✅
        ├── LANTERN_BASELINE_ANDROID [masked] [protected] ✅
        └── LANTERN_BASELINE_IOS     [masked] [protected] ✅
```

```
# ✅ CORRECTED PIPELINE — no secrets in YAML
# LANTERN_API_KEY injected automatically by GitLab on protected branches/tags
```

> **How this works:** GitLab CI/CD variables marked as `protected` are only injected into pipelines running on protected refs (branches/tags defined in GitLab's protected branch settings). Variables marked as `masked` are redacted from job logs so the key never appears in plain text. The YAML file itself contains no secrets — the runner receives the key automatically at runtime without it ever touching the repository. This satisfies Kestrel's company policy (E3) and eliminates the exposure risk from the draft pipeline.

### 4.3 Variable Availability Matrix

```
┌─────────────────────────────┬─────────────────────────────────────────┐
│ Pipeline context            │ Protected variable available?           │
├─────────────────────────────┼─────────────────────────────────────────┤
│ main branch (scheduled)     │ ✅ Yes                                  │
│ release/* branch            │ ✅ Yes                                  │
│ v* tag                      │ ✅ Yes                                  │
│ Internal MR branch          │ ✅ Yes                                  │
│ Fork MR (external contrib.) │ ❌ No — scan is skipped                 │
└─────────────────────────────┴─────────────────────────────────────────┘
```

> **Why fork MRs have no key:** GitLab deliberately withholds protected variables from pipelines triggered by forks. This is a security feature — an external contributor's fork could otherwise exfiltrate secrets by printing them in a job script. Since `LANTERN_API_KEY` is protected, it is simply absent in fork MR pipelines. The scan job must detect this and exit with `skip` rather than attempting to run and failing with exit code 3. This is not a Lantern limitation — it is a GitLab security boundary that the pipeline must handle gracefully.

---

## 5. Baseline Lifecycle

### 5.1 What Is a Baseline?

A baseline is a completed Lantern scan used as a reference point. When `--baseline <scan_id>` is passed, findings whose **fingerprint** already exists in the baseline scan are excluded from the count. This implements Kestrel's policy: **block only on new findings** (E4, R4).

### 5.2 Lifecycle Flow

```
  Release N completes
         │
         ▼
  Lina reviews findings in Lantern dashboard
         │
         ▼
  Lina records accepted scan IDs in Jira KPAY
         │
         ├── LANTERN_BASELINE_ANDROID = "rel-4.N-android"
         └── LANTERN_BASELINE_IOS     = "rel-4.N-ios"
                    │
                    ▼
         Update protected CI variables in GitLab
                    │
                    ▼
  Next release uses new baseline
  → only findings NEW since release N will count
```

> **How to read this diagram:** After every release, Lina performs a two-step process. First, she reviews the Lantern scan results and records the accepted scan IDs in Jira KPAY alongside the release notes (E4). Second, she updates the two GitLab CI variables `LANTERN_BASELINE_ANDROID` and `LANTERN_BASELINE_IOS` to point to the new scan IDs. From that point, the next release gate will diff against the freshly accepted baseline — meaning any finding that existed in the last release is automatically excluded and only genuinely new findings will trigger a block. **If this step is skipped**, the next release will compare against a stale baseline (e.g. still pointing to 4.11 when 4.12 introduced new known findings) and could either block on findings that were already accepted, or miss new ones depending on the fingerprint match. This process must be a mandatory checklist item in the release runbook.

### 5.3 Current Baseline Values

| Variable | Value | Set after |
|---|---|---|
| `LANTERN_BASELINE_ANDROID` | `rel-4.11-android` | Release 4.11 (2026-09-30) |
| `LANTERN_BASELINE_IOS` | `rel-4.11-ios` | Release 4.11 (2026-09-30) |

> **Risk:** If Lina forgets to update these variables after a release, the next gate will compare against a stale baseline and may miss new findings. This must be part of the release checklist.

> **Risk:** If a baseline scan ID is entered incorrectly (e.g. a future ID that doesn't exist yet), the CLI exits `3` → `error`. See S08 for a concrete example.

---

## 6. Exit Code Policy

### 6.1 Exit Code Reference

```
┌──────────┬────────────────────────────────────────────────────────────┐
│ Exit     │ Meaning                                                    │
│ Code     │                                                            │
├──────────┼────────────────────────────────────────────────────────────┤
│    0     │ Scan completed. No counted finding at or above threshold.  │
│          │ OR scan submitted without --wait.                          │
│          │ OR no --fail-on given.                                     │
├──────────┼────────────────────────────────────────────────────────────┤
│    1     │ Scan completed. At least one counted finding at or above   │
│          │ threshold (open or confirmed status, not in baseline).     │
├──────────┼────────────────────────────────────────────────────────────┤
│    2     │ Scan error. OR --wait timed out after 60 minutes           │
│          │ (scan continues server-side).                              │
├──────────┼────────────────────────────────────────────────────────────┤
│    3     │ Config/auth error BEFORE submission: missing key, revoked  │
│          │ key, missing file, unknown plan, baseline not found,       │
│          │ invalid arguments.                                         │
└──────────┴────────────────────────────────────────────────────────────┘
```

> **Why exit codes matter so much:** Exit codes are the only signal the pipeline receives from the CLI. A naive pipeline that uses `|| true` (as in the original draft) ignores exit codes entirely — if the API key is revoked (exit 3) or a scan times out (exit 2), the job still exits 0 and the pipeline turns green. Rafa's requirement R8 is specifically about this: the pipeline must never be green for the wrong reason. Exit codes 2 and 3 always surface as `error` — they do not pass, they do not block on a security finding, they pause the pipeline with a clear signal that something needs to be fixed before the release can proceed.

### 6.2 Gate Label by Pipeline × Exit Code

```
┌────────────────┬──────────┬──────────┬──────────┬──────────┐
│ Pipeline       │ Exit 0   │ Exit 1   │ Exit 2   │ Exit 3   │
├────────────────┼──────────┼──────────┼──────────┼──────────┤
│ Release        │  PASS    │  BLOCK   │  ERROR   │  ERROR   │
│ Nightly        │  REPORT  │  REPORT  │  ERROR   │  ERROR   │
│ MR (internal)  │  PASS    │  BLOCK   │  ERROR   │  ERROR   │
│ MR (fork)      │  SKIP    │  SKIP    │  SKIP    │  SKIP    │
└────────────────┴──────────┴──────────┴──────────┴──────────┘

⚠️  Exit codes 2 and 3 are ALWAYS error — never pass, never block.
⚠️  || true must never be used on Lantern scan commands (R8).
```

> **How to read this table:** Each cell defines the **gate label** — the single outcome assigned to a scan result based on the pipeline type and CLI exit code. `PASS` means the gate completed cleanly and the pipeline continues. `BLOCK` means a qualifying security finding was detected and the pipeline stops (publishing is prevented). `REPORT` means the result is recorded and routed (e.g. to Jira) but the pipeline is not stopped — this applies to all nightly outcomes because nightly is a monitoring run, not a gate. `ERROR` means the scan produced no usable result and the pipeline stops with a failure that is clearly technical rather than security-related — a reviewer seeing `ERROR` knows to look at keys, configuration, or scan duration, not at findings. `SKIP` applies to fork MRs where no scan runs at all, and the pipeline continues normally.

### 6.3 Finding Count Rules

Only findings with these criteria are **counted** toward exit code 1:

```
┌────────────────────────────────────────────────────────────────┐
│ A finding COUNTS if ALL of the following are true:             │
│                                                                │
│  ✅ severity >= threshold (e.g. high or critical)             │
│  ✅ status is "open" OR "confirmed"                           │
│  ✅ fingerprint NOT in the baseline scan                      │
│                                                                │
│ A finding does NOT count if any of the following:             │
│                                                                │
│  ❌ status is "false_positive"                                │
│  ❌ status is "risk_accepted"                                 │
│  ❌ status is "fixed"                                         │
│  ❌ fingerprint IS in the baseline (excluded_by_baseline)     │
│  ❌ severity is below threshold                               │
└────────────────────────────────────────────────────────────────┘
```

> **Why this distinction matters in practice:** A scan can return dozens of findings but zero *counted* findings — meaning the CLI exits 0 even though the report is non-empty. This is the expected and correct behaviour when all findings are either below the severity threshold, already known (in the baseline), triaged as false positives, or risk-accepted by the security team. A reviewer who sees `PASS` on a release with known vulnerabilities is not seeing a mistake — those vulnerabilities are tracked in Jira KPAY and the team has made a conscious decision about each one. The gate is designed to surface *new, unreviewed* risk, not to re-block on risk that has already been evaluated.

---

## 7. Prospect Requests R1–R8

### Summary Table

| # | Request | Status | Short answer |
|---|---|---|---|
| R1 | Block MR on high/critical mobile | ⚠️ Partly | Budget forces static-only on MR; full gate at release |
| R2 | SAST of `web/` and `api/` source code | ❌ Not supported | Lantern has no web/API SAST |
| R3 | Full GraphQL testing before signing | ❌ Not supported | Generic HTTP only, no roadmap date |
| R4 | Release blocks only on new findings | ✅ Supported | `--baseline` flag implements this |
| R5 | Full DAST of the App Store IPA | ❌ Not supported | App Store IPA is encrypted — static only |
| R6 | Automatic ServiceNow tickets | ❌ Not supported | "Exploring" — no committed date |
| R7 | SARIF artifact per release | ✅ Supported | `lantern export --format sarif` |
| R8 | No silent pass/fail | ✅ Supported | Exit 2/3 = error, `|| true` removed |

---

### Detailed Responses

#### R1 — Block MR on high/critical (mobile)
> *"Every merge request that introduces a high or critical finding should be blocked before merge, including the mobile apps."*

**⚠️ Partly supported.**

The MR pipeline has **2 minutes of remaining budget** (E2). A `mobile-full` scan takes 20–45 minutes (P9) — this is incompatible. The integration uses `mobile-static` on MR, which covers the majority of high/critical findings through static analysis and fits within the time budget. Full dynamic coverage runs on nightly and is enforced as a hard gate on release.

**Workable alternative:** Any finding missed by static analysis on MR will be caught by the nightly `mobile-full` scan and blocked at the release gate. The security posture is enforced before any build reaches production.

---

#### R2 — SAST of `web/` and `api/` source code
> *"Lantern should also scan the source code in `web/` and `api/` on each merge request."*

**❌ Not supported.**

Lantern performs **DAST only** on web and API targets — it tests running applications, not source code (P2). There is no source-code analysis (SAST) for web or API repositories.

**Workable alternative:** Add a dedicated SAST tool to the MR pipeline alongside Lantern — e.g. Semgrep (open source, GitLab-native SAST), SonarQube, or GitLab's built-in SAST. These run on source code and fit within MR pipelines. Lantern complements them by testing the running application dynamically.

---

#### R3 — GraphQL testing before signing
> *"We launch `/graphql` in November. Please confirm Lantern tests GraphQL properly before we sign."*

**❌ Not supported.**

Lantern scans a GraphQL endpoint as **generic HTTP traffic only**. There is no GraphQL-specific introspection, mutation fuzzing, or schema-aware testing (P2). No roadmap date has been supplied, and none can be committed (P11).

**Workable alternative:** Evaluate GraphQL-specific tools (e.g. Escape, Inigo) as a complement for the `/graphql` endpoint after its November launch.

---

#### R4 — Release blocks only on new findings
> *"Releases must block only on new high or critical findings. Known ones are already tracked in Jira."*

**✅ Supported.**

The `--baseline <scan_id>` flag (P7) compares the current scan against a previous scan. Findings whose fingerprint already appears in the baseline are listed as `excluded_by_baseline` and never count toward exit code 1. The release gate uses `$LANTERN_BASELINE_ANDROID` and `$LANTERN_BASELINE_IOS` CI variables maintained by Lina after each release.

---

#### R5 — Full DAST of the App Store IPA
> *"I want full dynamic testing of the exact iOS build we submit to the App Store."*

**❌ Not supported.**

App Store IPAs are encrypted by Apple. Lantern cannot instrument them for dynamic analysis and performs **static analysis only** — DAST is automatically skipped and reported as such in the scan result (P1).

**Workable alternative:** The nightly pipeline scans the **ad-hoc signed IPA** with `mobile-full` (static + dynamic). This is the same codebase, built from the same branch, with the same logic — only the distribution signing differs. Nightly DAST results on the ad-hoc IPA provide the dynamic coverage Imane is looking for.

---

#### R6 — Automatic ServiceNow tickets
> *"My security operations team works in ServiceNow. Findings should create ServiceNow tickets automatically."*

**❌ Not supported.**

Lantern has no ServiceNow integration. The roadmap lists it as "exploring" — no committed date exists, and none can be promised (P10, P11).

**Workable alternative:** Lantern's **Jira Cloud integration** provides two-way status sync — findings open Jira tickets in KPAY automatically, and when a finding is fixed or accepted in Lantern, the Jira ticket updates. The security operations team can mirror critical Jira issues to ServiceNow via Jira's native ServiceNow connector or a lightweight automation rule. SARIF exports are also available for any custom integration pipeline.

---

#### R7 — SARIF artifact per release
> *"Keep a SARIF file for every release in the pipeline artifacts so auditors can see what was checked."*

**✅ Supported.**

After the release gate passes, `lantern export --scan-id $LANTERN_SCAN_ID --format sarif --out lantern-release.sarif` downloads the full SARIF 2.1.0 report (P10). It is stored as a GitLab pipeline artifact with `expire_in: 1 year` for audit retention.

---

#### R8 — No silent pass or silent fail
> *"If the scanner breaks, I want to know, but it must not quietly turn the pipeline green or red for the wrong reason."*

**✅ Supported.**

The corrected pipeline removes all `|| true` constructs from Lantern scan commands. Exit codes 2 and 3 are explicitly handled as `error` — they never produce a green pipeline (pass) or a spurious red one (block on a security finding). Each label has a distinct reason and a defined remediation path.

---

## 8. Dependencies & Action Items

```
┌────┬────────────────────────────────────────────────────────┬───────┬──────────────┐
│ #  │ Action                                                 │ Owner │ Deadline     │
├────┼────────────────────────────────────────────────────────┼───────┼──────────────┤
│ A1 │ Revoke hardcoded API key lk_live_7f3c9d1e...          │ Rafa  │ Immediately  │
│ A2 │ Generate new key from Lantern dashboard                │ Rafa  │ Immediately  │
│ A3 │ Create LANTERN_API_KEY as masked+protected CI var      │ Rafa  │ Before run   │
│ A4 │ Create LANTERN_BASELINE_ANDROID CI variable            │ Rafa  │ Before run   │
│ A5 │ Create LANTERN_BASELINE_IOS CI variable                │ Rafa  │ Before run   │
│ A6 │ Submit Lantern egress IP allowlist request (staging)   │ Imane │ Immediately  │
│    │ (~5 business days, E5)                                 │       │              │
│ A7 │ Verify ci-scanner token is valid in staging-ci-token   │ Imane │ Before nightly│
│ A8 │ Add baseline update to release checklist               │ Lina  │ Before rel.  │
│ A9 │ Update LANTERN_BASELINE_* vars after each release      │ Lina  │ Post-release │
│A10 │ Record accepted Lantern scan IDs in Jira KPAY          │ Lina  │ Post-release │
└────┴────────────────────────────────────────────────────────┴───────┴──────────────┘
```

---

## Appendix — Fact Reference Index

| Fact ID | Used in |
|---|---|
| E2 | MR time budget, nightly window, release 90-min limit |
| E3 | Protected variables, fork MR key unavailability |
| E4 | Release gate policy, baseline IDs, Lina's role |
| E5 | Staging network isolation, allowlist requirement |
| E6 | MFA on qa-auto, use of ci-scanner token |
| E7 | Runner tags per job |
| E8 | Jira KPAY tracking, artifact retention |
| P1 | iOS IPA types, App Store static-only limitation |
| P2 | No web/API SAST, GraphQL generic HTTP only |
| P3 | Lantern SaaS-only, scanners from egress IPs |
| P4 | CLI flags, --wait 60-min cap |
| P5 | Exit codes 0/1/2/3 |
| P6 | Finding statuses that count vs. don't count |
| P7 | Baseline comparison, excluded_by_baseline |
| P8 | LANTERN_API_KEY env var, revocation |
| P9 | Scan duration estimates |
| P10 | Export formats, Jira integration, no ServiceNow |
| P11 | Pre-sales role boundary, no roadmap promises |

---

*This document is a pre-sales design aid for the Lantern trial. It does not constitute a contract, SLA, or feature commitment. All companies, people, keys and findings referenced are fictional.*
