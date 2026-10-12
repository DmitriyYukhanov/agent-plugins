---
name: implementation-prd
description: >
  Create implementation-ready PRD/spec bundles for new apps, products,
  services, platforms, mobile or desktop software, SaaS systems, or complex
  features. Use when the user asks for a detailed PRD, build-ready spec, spec
  bundle, spec packet, PRD + contracts + schema + test plan, backend or API
  spec, frontend or mobile app spec, feature requirements, technical product
  brief, or documentation that Claude Code or Codex can implement with minimal
  follow-up or one-shot implementation. Produce a decisive bundle with PRD,
  contracts, storage or data-model artifact, test plan, acceptance criteria,
  default technical choices, and phased implementation order.
---

# Implementation PRD

Write specs that another coding agent can execute without reopening discovery.

## Default Output

Create or update a spec bundle with these files:

1. `<slug>_prd.md`
2. `<slug>_contracts.md`
3. one storage artifact:
   - `<slug>_schema.sql` for SQL-backed systems;
   - `<slug>_data-model.md` for frontend-only work, NoSQL systems, or features with no relational schema change.
4. `<slug>_testplan.md`

Do not omit state design. If there is no durable storage delta, use the data-model artifact and state explicitly where state lives and why no schema change is needed.

When starting from scratch, use the bundled scaffold script.

Locate this installed `SKILL.md` through the current host's skill metadata or file tools. Resolve `../..` from its directory to get the absolute plugin root. Replace `<absolute-plugin-root>` below with that path and verify `scripts/init-spec-bundle.sh` exists. If the resource is unavailable, report the missing path and stop; do not assume a host environment variable supplies it.

```bash
bash "<absolute-plugin-root>/scripts/init-spec-bundle.sh" <slug> <product|feature|system> [output_dir] [sql|data-model]
```

Quote an explicit output directory after resolving it to an absolute path. Keep the script's refusal to overwrite existing files; choose a new destination or update existing specs deliberately.

## Working Rules

- Decide early whether the request is a net-new product, a service or platform subsystem, or a complex feature inside an existing system.
- Mirror the user's language for prose. Keep code, contract types, enum values, and filenames in English unless the repo already uses another convention.
- Make explicit assumptions instead of leaving hidden gaps.
- Choose one recommended default architecture or stack when that removes downstream ambiguity. Do not present option menus unless the user asked for trade-off analysis.
- Keep MVP and non-goals sharp. Downstream implementation should know what not to build.
- Make surfaces explicit. A surface can be a UI screen, route, API endpoint, CLI command, webhook, worker job, admin panel, SDK entry point, or automation hook.

## Bundle Workflow

1. Normalize inputs: problem, persona or caller/operator, target action, constraints, monetization or entitlement, integrations, data sensitivity, and delivery surface.
2. Draft the PRD first. Lock scope, scenarios, functional requirements, architecture, business rules, acceptance criteria, epics, implementation order, default technical decisions, risks, and Definition of Done.
3. Derive contracts from the PRD. Cover domain types, service boundaries, API or IPC payloads, async job events, validation rules, and error envelopes.
4. Derive the storage or data model artifact. Add durable entities, invariants, lifecycle states, and migration notes, or explicitly state that no schema change is needed and how state is represented.
5. Derive the test plan from critical paths and failure modes. Cover fixtures, unit, integration, E2E, snapshots or golden tests when rendering or formatting matters, performance or smoke, negative cases, and exit criteria.
6. Cross-check the files so naming, state machines, IDs, limits, and enum values match exactly.

## One-Shot Quality Gates

Before finishing, verify all of these:

- Scope, non-goals, and acceptance criteria are objective and testable.
- Every non-trivial user, caller, or operator flow has a happy path and at least one failure path.
- Long-running or async stages define job state, retry behavior, error reporting, and restart safety.
- Security, privacy, entitlement, billing, or quota rules are explicit when relevant.
- Contracts are serializable and precise enough for direct implementation.
- The spec contains default decisions, not TODOs disguised as choices.
- The test plan can prove the acceptance criteria, not just restate them.
- The Definition of Done includes code, contract or data-model updates, tests, error handling, surface or entry-point exposure, and persistence or restart behavior where applicable.

## References

- Read [references/spec-bundle-blueprint.md](references/spec-bundle-blueprint.md) for the canonical bundle structure and section-by-section expectations.
- Read [references/quality-gates.md](references/quality-gates.md) before finalizing any bundle that should be handed to a coding agent.

## Templates

Use the templates under `assets/templates/` when you need to scaffold or compare file structure:

- `product-prd-template.md`
- `system-prd-template.md`
- `feature-prd-template.md`
- `contracts-template.md`
- `schema-template.sql`
- `data-model-template.md`
- `testplan-template.md`
