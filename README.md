# Design a prospect's CI/CD integration

You are the Pre-Sales Engineer for the fictional vendor Lantern. Kestrel Pay, a fictional fintech prospect, is starting a 14-day trial. Its platform team pushed a draft GitLab pipeline that calls the Lantern CLI. Before it runs, design an integration that fits Kestrel's constraints, fix the draft, and check your pipeline decisions against nine recorded scan scenarios. The scenario snapshot is **2026-10-19 09:00 UTC**, separate from your assessment deadline.

## Timing and setup

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is visible through follow-through and verification.

Inputs:

- [Kestrel environment facts](inputs/environment.md) (E1–E9)
- [Lantern product and CLI facts](inputs/product.md) (P1–P12)
- [Prospect requests](inputs/requests.md) (R1–R8)
- [Current draft pipeline](inputs/current.gitlab-ci.yml)
- Scan scenarios in `inputs/scenarios/batch1/` (S01–S06) and `inputs/scenarios/batch2/` (S07–S09)
- [Optional offline CLI mock](inputs/lantern_mock.py)

Baseline skills: application security scanning concepts (static versus dynamic analysis, authenticated scanning, baselines and false positives), GitLab CI or similar pipeline YAML, and reading JSON. **No programming is required.** A text editor is enough.

Each scenario has a `context` block (which pipeline, ref, fork status, runner, artifact and which CI variables the job would see) and a `lantern` block (what the service would return: key validity, baselines, outcome and findings). With the CLI rules in P4–P8 you can work out by reading each file what the CLI would return for the command your pipeline runs. If you have Python 3.10+, the optional mock applies the same rules and shows the result; from the exported `candidate/` directory, for example:

```
LANTERN_API_KEY=demo python3 inputs/lantern_mock.py --scenario inputs/scenarios/batch1/S01-release-android.json scan mobile --file android/app/build/outputs/bundle/release/app-release.aab --plan mobile-full --wait --fail-on high
```

Using the mock is not required and earns no extra marks. Do not edit the mock or the scenarios. All companies, people, keys and findings are fictional. Outside research is optional and cannot affect marks.

## Core task

1. **Integration design** (about two pages). For merge request, nightly and release pipelines, state which Lantern scans run, on which artifact or target, with which flags, whether they block, and how they fit the time budget. Cover secrets handling, the baseline lifecycle, and an exit-code policy for 0/1/2/3 that never turns a pipeline green or red for the wrong reason. Answer every request R1–R8 as supported, partly supported or not supported, with the honest alternative. List dependencies Kestrel must complete, with an owner.
2. **Revised pipeline.** Deliver a corrected GitLab CI file and a short list of every problem you fixed in the draft, with the fact ID that shows why. It does not need to run against GitLab; it must be valid YAML and consistent with your design.
3. **Gate decision table.** Write your gate policy as a decision table (or a short flowchart) that another engineer could apply without asking you. It reads the pipeline context and the CLI result (pipeline type, fork, key available, exit code, `submitted` status, baseline, counted findings) and gives exactly one label with a reason: `pass` (gate completed, nothing at or above the policy threshold), `block` (pipeline must stop for a security finding), `report` (findings recorded and routed, pipeline continues), `error` (no usable result; never treated as a pass) or `skip` (scan intentionally not run, with reason). Apply it to batch 1 (S01–S06). For each scenario, record the command your pipeline would run, the exit code and counted findings you expect with the P-facts that explain them, the label and a one-line reason.
4. **Second batch.** Apply the same table to batch 2 (S07–S09). Record anything you had to add to or change in the table, and why. Keep both result sets.
5. **Prospect message.** Draft a message of at most 200 words to Rafa explaining the plan, what Lantern will and will not do, and the actions Kestrel must take. Label it **draft; do not send**.

Do not promise unsupported features, roadmap dates or detection guarantees. Do not contact anyone, scan anything or use real keys. The leaked key in the draft is fictional; treat it as you would a real one.

## Submission and acceptance

Submit an archive or repository with the design, revised pipeline and change list, decision table with the results for both batches, the prospect draft, and a concise work/AI-use log. If you used the mock or wrote a script, include the commands you ran. Add a 3–5 minute recorded walkthrough **or equivalent accessible text** explaining one design tradeoff and one check.

Acceptance: a reviewer who applies your table to any scenario gets your label; expected exit codes follow P4–P8; every scenario has one label and reason; exit codes 2 and 3 never become `pass`; the release gate follows E4; the design respects every time budget and secrets rule; unsupported asks are stated plainly with a workable alternative.

Your work log records prioritization, one obstacle and response, one validation or refinement, limits and a next step. No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for design, YAML and critique; tool choice is not graded. Check its output against the facts. Include a short AI-use note naming the tool and one output you accepted, corrected or rejected, with the reason. If you used no AI, say so; do not fabricate an AI failure. Do not submit full prompt histories or personal account access.

Scoring: **usable result 40; accuracy/verification 25; prioritization 20; communication/handoff 15**. Full marks are possible on the core alone. No marks for volume, hours worked, software choice, writing code, AI detection or prose polish. Optional stretch: a one-page trial success checklist for Kestrel; not needed for full marks.
