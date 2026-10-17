# Prospect Message — Rafa, Kestrel Pay

**draft; do not send**

---

Hi Rafa,

Thanks for sharing the draft pipeline — I've gone through it and put together the integration
plan for the trial. Here's where we land.

On the pipeline side, every MR will run a fast static scan on the Android build and block if
something new and high or critical shows up. Nightly, we go deeper — full static and dynamic
scans on Android, iOS, and your staging environment — but nothing blocks there, it's purely
visibility. Then at release time, both the Android and iOS builds go through the full gate
against your last accepted baseline, so only genuinely new high or critical findings hold up
a release. SARIF files get stored as artifacts on every release for your auditors.

A few things I want to be upfront about: Lantern doesn't do source code analysis on your
web or API repos, so that's a gap you'd want to fill with something like Semgrep or GitLab
SAST. The App Store IPA can only be scanned statically — Apple's encryption blocks dynamic
analysis — but the nightly ad-hoc build covers that. And ServiceNow isn't integrated yet;
Jira Cloud is the native option for now.

Before anything runs, there are a few things your team needs to handle: the API key in the
draft pipeline needs to be revoked and moved to a protected CI variable, Imane needs to file
the allowlist request for staging (that takes about 5 days), and Lina should plan to update
the baseline variables after each release.

Let me know if you want to jump on a call to walk through any of this.

Cheers

---

*Word count: 199*
