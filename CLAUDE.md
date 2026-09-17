# Encore: project instructions

Non-commercial data portfolio project analyzing how bands use their catalog in live shows.

Read these before any task:
- @docs/context/product.md
- @docs/context/tech.md
- @docs/context/structure.md

Specs live in `docs/specs/`. Implement one spec at a time, only after the plan is approved.

## Working rules

- Always plan first and wait for approval before writing code for a spec.
- Work in small steps and commit after each completed task with a clear message in English.
- Never commit `.env`, `data/`, or notebook outputs.
- Never persist setlist.fm data outside the ephemeral `raw_setlistfm` schema.
- Never bind ports to 0.0.0.0.
- Every Docker image must support linux/arm64.
- Run the tests before declaring a task done.
- If something in a spec is ambiguous or conflicts with the context files, ask instead of guessing.
