# Claude project notes — ansible-role-netbox-bootstrap

This is an Ansible role that idempotently bootstraps a fresh NetBox instance
from declarative YAML variable files. It covers users, groups, object
permissions, custom fields, tags, webhooks, export templates, DCIM structure,
IPAM structure, and tenancy. A companion Python CLI (`scripts/export_netbox.py`)
snapshots any live NetBox instance into those YAML files.

## Working guidelines

These four principles address common LLM coding pitfalls. They apply to every
task in this repo — Ansible tasks, export script changes, and documentation.
Bias toward caution over speed; for trivial one-liners, use judgment.

### 1. Think before coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

* State assumptions explicitly. If uncertain about NetBox API behavior,
  collection module reliability, or the correct `uri`-vs-collection choice
  for a section, ask before writing code.
* If multiple interpretations exist, present them — don't pick silently.
* If a simpler approach exists, say so. Push back when warranted.
* If something in the task or schema is unclear, stop. Name what's confusing.
  Check `DESIGN.md` first; if still unclear, ask.

### 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

* One module call per logical task. Don't combine multiple API calls in a
  single `uri` task when two separate tasks are clearer.
* No Jinja2 complexity beyond what the task requires.
* No export script features or CLI options that weren't asked for.
* No "flexibility" or extra variables that weren't requested.
* If a task can be expressed in 5 lines, don't write 20.

Ask: "Would a senior Ansible engineer say this is overcomplicated?" If yes,
simplify.

### 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

* When fixing or adding a section task, don't "improve" adjacent task files,
  comments, or formatting.
* Don't reorder the include chain in `tasks/main.yml` unless the change
  explicitly requires it — the dependency order is load-bearing.
* Match existing YAML style, even if you'd do it differently.
* If you notice a linting issue or dead code in an unrelated file, mention it —
  don't fix it as a side effect of an unrelated commit.
* Remove only imports, variables, or blocks that YOUR change made unused.

Every changed line should trace directly to the stated task.

### 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals before starting:

* "Add a new section" → task file written, `pre-commit run --all-files`
  passes, role runs idempotently against a fresh NetBox instance, existing
  sections still run clean.
* "Fix an export cleaner" → exported YAML matches expected shape, existing
  `vars/*.yml` load without Ansible error, `--dry-run` output is correct.
* "Update the CLI" → `--help` reflects the change, `.env` override works,
  explicit flag overrides `.env`, `pre-commit run` passes.

For multi-step work, state a brief plan with verify steps before starting:

    1. [Step] → verify: [check]
    2. [Step] → verify: [check]

Strong success criteria allow independent looping. Weak criteria ("make it
work") require constant clarification.

---

## Source of truth

**`DESIGN.md`** in this repo is the authoritative spec. Read it before making
any non-trivial change. Section scope, dependency ordering, export script
design, var file schema, and the `uri` vs `netbox.netbox` collection split all
live there.

If something in the code disagrees with `DESIGN.md`, `DESIGN.md` is right
unless explicitly told otherwise — flag the discrepancy and ask before "fixing"
the design to match the code.

## Repo state

The role skeleton is complete:

* `tasks/preflight.yml` + all 22 section task files are written
* `tasks/main.yml` orchestrates preflight then all sections in strict
  dependency order (see DESIGN.md §6)
* `defaults/main.yml` defines the full public interface
* `vars/*.yml` are populated stubs — every file exists with an empty list.
  They must be populated by running `scripts/export_netbox.py` against a
  live source instance before the role is useful.
* `scripts/export_netbox.py` is the Click CLI export tool; `scripts/.env`
  is gitignored and must be created locally from `scripts/.env.example`.

**Immediate next steps:**

1. Verify `scripts/.env` is not tracked (`git status` — it must not appear).
2. Run `scripts/export_netbox.py` against the source NetBox instance to
   populate `vars/*.yml`.
3. Commit the populated var files.
4. Run the role against a fresh NetBox container to validate end-to-end.
5. Add a `molecule/` scenario once the role is validated manually.

## Conventions

* **Commits**: follow the commit message guide in this file exactly.
  Conventional Commits, imperative mood, bodies wrapped at 72 characters,
  asterisk bullets.
* **Lint**: `.ansible-lint`, `.yamllint`, `.pre-commit-config.yaml` define
  the rules. Run `pre-commit run --all-files` before declaring work done.
* **Secrets**: never write a credential into a tracked file. `netbox_api_token`
  lives in Ansible Vault on the consumer side; `scripts/.env` is gitignored.
  Use `no_log: true` on any task that touches `netbox_api_token`.
* **Modules**: prefer FQCNs — `ansible.builtin.*`, `netbox.netbox.*`,
  `ansible.builtin.uri`. The `.ansible-lint` `fqcn-builtins` rule enforces it.
* **Collection vs uri**: use `netbox.netbox` collection modules where they are
  reliable (tags, custom fields, webhooks, all DCIM/IPAM/tenancy objects).
  Use `ansible.builtin.uri` for groups, permissions, custom links, and export
  templates where collection support is absent or unreliable. See DESIGN.md §1
  for the full per-section table.
* **Var files**: `vars/*.yml` are generated by the export script. Never
  hand-edit them to reflect what is in NetBox — always re-run the export
  script. Hand-edits will be silently overwritten on the next export.
* **Idempotency**: every task must be safe to re-run. Objects not present in
  the var files are left untouched — the role never deletes.
* **Var naming**: `netbox_url`, `netbox_api_token`, and `netbox_validate_certs`
  are intentionally unprefixed for cross-role reuse. `var-naming` is skipped
  in `.ansible-lint` for this reason. Do not rename these to `netbox_bootstrap_*`.

## Settled decisions — don't re-litigate

These are locked in `DESIGN.md`. Don't propose alternatives unless the human
raises them:

* Export tool = Python + Click + environs. Not an Ansible playbook.
* `.env` loads from the script's own directory (`scripts/`), not cwd.
* `netbox.netbox` collection preferred; `ansible.builtin.uri` for the four
  sections with collection gaps (groups, permissions, custom links, export
  templates).
* Var file schema: one YAML file per section, top-level key matching section
  name, no `id`/`url`/`display` fields, nested objects collapsed to slug or
  name.
* No destructive cleanup: objects in NetBox not present in var files are left
  alone.
* Section dependency order is strict and enforced in `tasks/main.yml`. Do not
  reorder.
* `var-naming` ansible-lint rule is skipped — shared connection variables
  (`netbox_url`, `netbox_api_token`) are intentionally unprefixed.

## Open questions tracked in DESIGN.md

If a task touches one of these, leave a `# TODO(open-q):` comment linking to
the section rather than guessing:

* Config contexts (`/api/extras/config-contexts/`) — deferred to a future
  Tier 6; not currently in scope.
* Multi-instance Click profiles (`--profile production`) — future subcommand
  work.
* Scheduled export mechanism (cron vs Cowork scheduled task).

## Testing locally

* `pre-commit run --all-files` — lint/format pass. Run before every commit.
* Run `scripts/export_netbox.py --dry-run --verbose` to validate connectivity
  and inspect output before writing files.
* Manual role run: `ansible-playbook bootstrap_netbox.yml --ask-vault-pass`
  against a fresh NetBox container.
* `molecule test` — full scenario per platform (not yet written; flag when
  ready).

## When in doubt

Read `DESIGN.md`, then ask.

---

## Commit message guide

You are an expert DevOps engineer and professional git commit message writer.
When generating a commit message, follow these steps exactly.

### Step 1 — Retrieve changes

Run:

    git diff --cached

Analyze the full staged diff. This is the **single source of truth** for what
will be committed.

### Step 2 — Understand the change

Determine:

* The **primary purpose** of the change
* The **type of change** (feature, bug fix, refactor, etc.)
* The **most relevant scope** within the role or export script
* Whether the change introduces a **breaking change** for role consumers
* Whether multiple changes should be summarized together

Pay special attention to:

* Changes to `defaults/main.yml` — these define the role's public interface
* Changes to var file schema in `vars/*.yml` — a schema change breaks existing
  exported YAML and requires a re-export from all source instances
* Changes to section names — section names are the values passed to
  `export_netbox.py --sections` and referenced in toggle variable names
* Changes to the export script CLI interface — consumers may script around it
* Changes to task names or tags that consumers may pin to

If multiple files are modified, identify the **dominant intent** rather than
listing every file.

### Step 3 — Select commit type

Use Conventional Commits:

* `feat` — new section, new task, new export capability, new CLI option
* `fix` — bug fix, idempotency correction, cleaner error handling
* `docs` — README, DESIGN.md, CLAUDE.md, inline comments
* `style` — YAML formatting, whitespace, ansible-lint cleanup
* `refactor` — restructure tasks or script without behavior change
* `perf` — reduced API calls, pagination improvements, faster export
* `test` — molecule scenarios, lint config, CI tests
* `chore` — galaxy metadata, dependencies, tooling, pre-commit hook versions
* `ci` — GitHub Actions, GitLab CI, pre-commit hooks

### Step 4 — Determine scope

Infer a scope from the role layout or NetBox subsystem.

Common Ansible role scopes: `tasks`, `defaults`, `vars`, `meta`, `preflight`,
`scripts`.

Common NetBox section scopes (match the section key names exactly):
`users`, `groups`, `permissions`, `tags`, `custom-fields`, `custom-links`,
`webhooks`, `export-templates`, `tenant-groups`, `tenants`, `regions`,
`site-groups`, `sites`, `locations`, `rack-roles`, `device-roles`,
`platforms`, `rirs`, `aggregates`, `vrfs`, `route-targets`, `vlan-groups`.

Export script scopes: `export`, `cli`, `cleaners`.

Only include a scope when it adds clarity. Prefer the NetBox section scope
for section-driven changes (e.g., `feat(permissions): ...`) and the role
layout scope for structural changes (e.g., `refactor(tasks): ...`).

### Step 5 — Write the commit message

Format exactly as:

    <type>[optional scope]: <short summary (<=50 chars)>

    <body wrapped at 72 characters>

    [optional footer(s)]

**Subject line rules:**

* Use **imperative mood** ("Add", "Fix", "Update", "Remove", "Populate")
* Maximum **50 characters**
* Describe the **result**, not the implementation
* Prefer NetBox or Ansible terminology over generic phrasing
  (e.g., "Add object permissions section", not "Add new task file")

**Body rules** (required):

Explain **why the change was made**, focusing on:

* What NetBox API behavior or Ansible limitation motivated it
* What downstream role consumers or export script users need to know
* Any NetBox version constraints or collection version requirements

When helpful, summarize key changes using bullet points.

**Bullet rules:**

* Use `*` (asterisk) for all bullets — never `-` or `•`
* Nested bullets indented with two spaces
* No Markdown formatting of any kind

Example:

    * Add groups section task using ansible.builtin.uri
    * Add permissions section task with idempotency pre-fetch
      * Permissions matched by name; existing objects patched

**Ansible-specific expectations:**

* Call out new, renamed, or removed default variables
* Note when section toggle variable names change
  (e.g., `netbox_bootstrap_groups` renamed)
* Mention idempotency improvements when relevant
* Note collection vs uri method when adding or changing a section
* Flag changes to `meta/main.yml` (galaxy metadata, minimum Ansible version,
  supported platforms)
* Note molecule scenario additions or removals

**NetBox-specific expectations:**

* Distinguish changes that require a re-export from the source instance
  from changes that are safe to apply to existing var files
* Note the minimum NetBox version when using API endpoints added in a
  specific release
* Call out new API endpoints by path when adding sections
* Highlight changes to the `uri`-vs-collection split decisions
* Note changes to the data-cleaning logic in `export_netbox.py` that affect
  the shape of var file output — consumers with committed var files will
  need to re-export

**Export script-specific expectations:**

* Note new or removed CLI options (they may be scripted by consumers)
* Highlight changes to `.env` variable names
* Call out changes to the section registry that add or remove valid
  `--sections` values

### Breaking changes

A change is breaking when it:

* Renames or removes a `defaults/main.yml` variable
* Renames a section key (breaks `--sections` CLI values and toggle var names)
* Changes the var file schema in a way that makes existing exported YAML
  invalid (requires a re-export from all source instances)
* Removes or renames a CLI option in `export_netbox.py`
* Renames or removes an `.env` variable name
* Drops support for a NetBox or Ansible version
* Changes the dependency order between sections in a way that breaks
  existing playbooks that run a subset of sections

If the diff introduces a breaking change:

* Add `!` after the type/scope in the subject
* Include a footer: `BREAKING CHANGE: <description>`

Examples:

    feat(permissions): add object permissions section
    fix(cleaners): preserve constraints field in permissions export
    refactor(tasks): split uri tasks into separate pre-fetch pattern
    chore(meta): update supported platforms list
    test(molecule): add default scenario for Ubuntu 24.04
    docs(README): add vault setup example for bootstrap password

    feat(export)!: rename NETBOX_SECTIONS env var to NETBOX_EXPORT_SECTIONS

    BREAKING CHANGE: NETBOX_SECTIONS is now NETBOX_EXPORT_SECTIONS in
    .env and as the envvar for --sections; update .env files before
    upgrading.

    feat(vars)!: change nested object format from slug to name

    BREAKING CHANGE: var file schema now uses name instead of slug for
    nested related objects; existing vars/*.yml must be regenerated by
    re-running the export script against the source instance.

### Step 6 — Output rules

Return **only the commit message** — no explanation, no analysis, no diff,
no markdown formatting, no code fences. The output will be pasted directly
into a git commit editor.
