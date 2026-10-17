# Kestrel Pay trial requests

Asks collected at the technical kickoff on 2026-10-16. Each request is the prospect's wording, not a statement of what Lantern supports.

- **R1, Rafa:** "Every merge request that introduces a high or critical finding should be blocked before merge, including the mobile apps."
- **R2, Imane:** "Lantern should also scan the source code in `web/` and `api/` on each merge request, the same way our linters do."
- **R3, Rafa:** "We launch `/graphql` in November. Please confirm Lantern tests GraphQL properly before we sign."
- **R4, Imane:** "Releases must block only on new high or critical findings. Known ones are already tracked in Jira."
- **R5, Imane:** "I want full dynamic testing of the exact iOS build we submit to the App Store."
- **R6, Imane:** "My security operations team works in ServiceNow. Findings should create ServiceNow tickets automatically."
- **R7, Rafa:** "Keep a SARIF file for every release in the pipeline artifacts so auditors can see what was checked."
- **R8, Rafa:** "Don't make me babysit this. If the scanner breaks, I want to know, but it must not quietly turn the pipeline green or red for the wrong reason."
