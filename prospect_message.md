# Prospect Message — Rafa, Kestrel Pay

**draft; do not send**

---

Hi Rafa,

Here is the integration plan for your Lantern trial.

**What Lantern will do:**
Merge request pipelines run a fast static scan on the Android debug build and block on new
high or critical findings. Nightly pipelines run full static and dynamic scans on Android,
iOS (ad-hoc build), and your staging web and API — findings are recorded without blocking.
Release pipelines gate both the Android AAB and the iOS App Store IPA against your last
accepted baseline, blocking only on genuinely new high or critical findings. SARIF reports
are stored as pipeline artifacts for every release.

**What Lantern will not do:**
Lantern does not analyse web or API source code (SAST). The App Store IPA receives static
analysis only — dynamic testing is not possible on an encrypted binary; use the nightly
ad-hoc build for that coverage. There is no ServiceNow integration at this time; Jira Cloud
two-way sync is available. GraphQL-specific testing is not supported.

**Actions required from Kestrel before the first run:**
- Revoke the API key currently hardcoded in the draft pipeline and generate a new one
- Store it as a masked, protected CI variable (`LANTERN_API_KEY`)
- Add `LANTERN_BASELINE_ANDROID` and `LANTERN_BASELINE_IOS` as protected CI variables
- File the Lantern egress IP allowlist request for `staging.kestrel.test` (Imane, ~5 days)
- After each release, Lina updates both baseline variables to the new scan IDs

Happy to walk through any of this on a call.

Best regards

---

*Word count: 199*
