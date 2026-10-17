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

> **Important:** The Lantern CLI does not scan from the runner machine. It submits the file or URL to the Lantern SaaS engine and waits for results (`--wait` blocks up to 60 minutes).

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
