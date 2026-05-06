# ansible-role-netbox-bootstrap — Architecture Design

## Overview

This role provides a repeatable, idempotent bootstrap of a fresh NetBox instance from
a declarative set of YAML variable files. The companion CLI tool (`scripts/export_netbox.py`)
snapshots the configuration of any live NetBox instance into those files, creating a
"configuration as code" workflow for NetBox deployments.

**Goals:**

- Any NetBox instance can be bootstrapped to a known, version-controlled state by running
  one Ansible playbook.
- The export script is the single mechanism for capturing live state — never hand-edit
  the var files to reflect what's in NetBox; always export.
- Scope is intentionally broad: users, permissions, IPAM structure, DCIM structure,
  tenancy, and extras (custom fields, tags, webhooks) are all covered.
- The `netbox.netbox` Ansible collection is preferred where modules exist and are
  reliable; `ansible.builtin.uri` is used where collection support is absent or weak
  (notably groups, object permissions, and some extras endpoints).
- Sensitive values (API tokens, passwords) are never stored in the var files; they live
  in Ansible Vault and are passed at runtime.

**Not in scope:**

- Device-level data (specific devices, interfaces, IP addresses, cables) — that is
  site-specific operational data, not boilerplate config.
- Manufacturer / Device Type library — handled separately by `nb-dt-import.py`
  (netbox-device-type-library).
- LDAP / SSO configuration — managed in `netbox_config.py` / `configuration/` of the
  NetBox deployment role, not here.

---

## 1. Bootstrap Scope

Sections are applied in dependency order. Each section maps 1:1 to a var file and a
task file.

### Tier 1 — Users & Access

Applied first; all other configuration may reference groups or be owned by users.

| Section       | NetBox API endpoint            | Collection module              | Method    |
|---------------|-------------------------------|-------------------------------|-----------|
| `groups`      | `/api/users/groups/`          | None reliable                 | `uri`     |
| `users`       | `/api/users/users/`           | `netbox.netbox.netbox_user`   | collection|
| `permissions` | `/api/users/permissions/`     | None                          | `uri`     |

> **Note on passwords:** User passwords are not exported (the API never returns them).
> On bootstrap, users are created with a generated random password and immediately
> marked inactive, or a vault-provided default password is set. Operators reset via
> Django admin or `manage.py changepassword` after first boot.

### Tier 2 — Extras & Configuration

Applied before structural objects because custom fields must exist before devices/IPs
that use them can be created.

| Section         | NetBox API endpoint              | Collection module                       | Method     |
|-----------------|----------------------------------|-----------------------------------------|------------|
| `tags`          | `/api/extras/tags/`              | `netbox.netbox.netbox_tag`              | collection |
| `custom_fields` | `/api/extras/custom-fields/`     | `netbox.netbox.netbox_custom_field`     | collection |
| `custom_links`  | `/api/extras/custom-links/`      | None                                    | `uri`      |
| `webhooks`      | `/api/extras/webhooks/`          | `netbox.netbox.netbox_webhook`          | collection |
| `export_templates` | `/api/extras/export-templates/` | None                                  | `uri`      |

### Tier 3 — Tenancy

| Section         | NetBox API endpoint              | Collection module                       | Method     |
|-----------------|----------------------------------|-----------------------------------------|------------|
| `tenant_groups` | `/api/tenancy/tenant-groups/`    | `netbox.netbox.netbox_tenant_group`     | collection |
| `tenants`       | `/api/tenancy/tenants/`          | `netbox.netbox.netbox_tenant`           | collection |

### Tier 4 — DCIM Structure

Infrastructure roles, sites, and regions — no individual devices.

| Section        | NetBox API endpoint           | Collection module                      | Method     |
|----------------|-------------------------------|----------------------------------------|------------|
| `regions`      | `/api/dcim/regions/`          | `netbox.netbox.netbox_region`          | collection |
| `site_groups`  | `/api/dcim/site-groups/`      | `netbox.netbox.netbox_site_group`      | collection |
| `sites`        | `/api/dcim/sites/`            | `netbox.netbox.netbox_site`            | collection |
| `locations`    | `/api/dcim/locations/`        | `netbox.netbox.netbox_location`        | collection |
| `rack_roles`   | `/api/dcim/rack-roles/`       | `netbox.netbox.netbox_rack_role`       | collection |
| `device_roles` | `/api/dcim/device-roles/`     | `netbox.netbox.netbox_device_role`     | collection |
| `platforms`    | `/api/dcim/platforms/`        | `netbox.netbox.netbox_platform`        | collection |

### Tier 5 — IPAM Structure

Structural IPAM objects only — no individual IP addresses or reservations.

| Section       | NetBox API endpoint           | Collection module                     | Method     |
|---------------|-------------------------------|---------------------------------------|------------|
| `rirs`        | `/api/ipam/rirs/`             | `netbox.netbox.netbox_rir`            | collection |
| `aggregates`  | `/api/ipam/aggregates/`       | `netbox.netbox.netbox_aggregate`      | collection |
| `vrfs`        | `/api/ipam/vrfs/`             | `netbox.netbox.netbox_vrf`            | collection |
| `route_targets` | `/api/ipam/route-targets/`  | `netbox.netbox.netbox_route_target`   | collection |
| `vlan_groups` | `/api/ipam/vlan-groups/`      | `netbox.netbox.netbox_vlan_group`     | collection |

---

## 2. Export Script Design (`scripts/export_netbox.py`)

### Why Python + Click, not Ansible

The export is a one-shot read/transform/write operation — not idempotent configuration
management. Python with Click is the right tool:

- Runs locally on any machine with network access to the source NetBox.
- Click provides clean `--url`, `--token`, `--output-dir`, `--sections` CLI flags with
  validation, help text, and future extensibility (subcommands, env var fallback, etc.).
- `pynetbox` handles pagination and object traversal automatically.
- YAML serialization is straightforward with `PyYAML`.
- No Ansible overhead or inventory required.

### CLI Interface

```
Usage: export_netbox.py [OPTIONS]

  Export NetBox configuration to YAML variable files.

Options:
  -u, --url TEXT        NetBox base URL  [required]
  -t, --token TEXT      API token (or set NETBOX_TOKEN env var)  [required]
  -o, --output-dir PATH Output directory for var files  [default: ./vars]
  -s, --sections TEXT   Comma-separated list of sections to export.
                        Omit to export all.
  --insecure            Disable TLS certificate verification
  --dry-run             Print what would be exported without writing files
  -v, --verbose         Verbose output
  --help                Show this message and exit.
```

**Token handling:** The token may be passed via `--token` or the `NETBOX_TOKEN`
environment variable. The full token string (including any prefix such as
`nbt_xxxx.`) is passed as-is in the `Authorization: Token <token>` header.
Tokens are never written to disk by the script.

**Future Click subcommands (planned):**

```
export_netbox.py export   # current behaviour — snapshot to YAML
export_netbox.py diff     # compare live instance against YAML files
export_netbox.py validate # validate YAML files against NetBox schema
```

### Data Cleaning

The export script strips fields that are instance-specific or should not be replicated:

- `id`, `url`, `display`, `created`, `last_updated` — synthetic/auto fields
- `password` — never returned by API anyway
- `token` — not exported from `/api/users/tokens/`
- Nested related objects are collapsed to their slug or name for Ansible idempotency
  (e.g. `{"id": 3, "name": "Printers", "slug": "printers"}` → `"printers"`)

### Output Format

One YAML file per section, written to `--output-dir` (default `vars/`):

```
vars/
  groups.yml
  users.yml
  permissions.yml
  tags.yml
  custom_fields.yml
  custom_links.yml
  webhooks.yml
  export_templates.yml
  tenant_groups.yml
  tenants.yml
  regions.yml
  site_groups.yml
  sites.yml
  locations.yml
  rack_roles.yml
  device_roles.yml
  platforms.yml
  rirs.yml
  aggregates.yml
  vrfs.yml
  route_targets.yml
  vlan_groups.yml
```

Each file contains a single top-level key matching the section name:

```yaml
# vars/device_roles.yml
device_roles:
  - name: Printer
    slug: printer
    color: "9e9e9e"
    vm_role: false
    description: ""
  - name: Unmanaged Hub
    slug: unmanaged-hub
    color: "ff9800"
    vm_role: false
    description: ""
```

---

## 3. Role Structure

```
ansible-role-netbox-bootstrap/
  defaults/
    main.yml              # netbox_url, netbox_api_token (vault ref), section toggles
  tasks/
    main.yml              # include_tasks per enabled section, in dependency order
    groups.yml
    users.yml
    permissions.yml
    tags.yml
    custom_fields.yml
    custom_links.yml
    webhooks.yml
    export_templates.yml
    tenant_groups.yml
    tenants.yml
    regions.yml
    site_groups.yml
    sites.yml
    locations.yml
    rack_roles.yml
    device_roles.yml
    platforms.yml
    rirs.yml
    aggregates.yml
    vrfs.yml
    route_targets.yml
    vlan_groups.yml
  vars/
    groups.yml            # populated by export script
    users.yml
    permissions.yml
    tags.yml
    custom_fields.yml
    custom_links.yml
    webhooks.yml
    export_templates.yml
    tenant_groups.yml
    tenants.yml
    regions.yml
    site_groups.yml
    sites.yml
    locations.yml
    rack_roles.yml
    device_roles.yml
    platforms.yml
    rirs.yml
    aggregates.yml
    vrfs.yml
    route_targets.yml
    vlan_groups.yml
  scripts/
    export_netbox.py      # Click export CLI
    requirements.txt      # click, pynetbox, pyyaml
  meta/
    main.yml              # galaxy metadata, dependencies
  README.md
  DESIGN.md
```

### defaults/main.yml

```yaml
# Connection
netbox_url: "https://netbox.example.com"
netbox_api_token: "{{ vault_netbox_api_token }}"
netbox_validate_certs: true

# Section toggles — set to false to skip a section
netbox_bootstrap_groups: true
netbox_bootstrap_users: true
netbox_bootstrap_permissions: true
netbox_bootstrap_tags: true
netbox_bootstrap_custom_fields: true
netbox_bootstrap_custom_links: true
netbox_bootstrap_webhooks: true
netbox_bootstrap_export_templates: true
netbox_bootstrap_tenant_groups: true
netbox_bootstrap_tenants: true
netbox_bootstrap_regions: true
netbox_bootstrap_site_groups: true
netbox_bootstrap_sites: true
netbox_bootstrap_locations: true
netbox_bootstrap_rack_roles: true
netbox_bootstrap_device_roles: true
netbox_bootstrap_platforms: true
netbox_bootstrap_rirs: true
netbox_bootstrap_aggregates: true
netbox_bootstrap_vrfs: true
netbox_bootstrap_route_targets: true
netbox_bootstrap_vlan_groups: true

# User bootstrap password (vault-encrypted)
# Users are created with this password and should change it on first login.
# Unused if netbox_bootstrap_users: false.
netbox_bootstrap_default_password: "{{ vault_netbox_bootstrap_default_password }}"
```

---

## 4. Workflow

### Initial Export (snapshot a source instance)

```bash
cd ansible-role-netbox-bootstrap/scripts
pip install -r requirements.txt

# Token via env var (preferred — keeps it out of shell history)
export NETBOX_TOKEN="nbt_xxxx.<your-token>"
python export_netbox.py \
  --url https://netbox.example.com \
  --output-dir ../vars

# Or selectively export only certain sections
python export_netbox.py \
  --url https://netbox.example.com \
  --sections users,groups,permissions,device_roles,custom_fields
```

Commit the resulting `vars/*.yml` to version control. These files are the source of
truth for the bootstrap configuration.

### Bootstrap a Fresh Instance

```bash
ansible-playbook bootstrap_netbox.yml \
  -i inventory/netbox_new.yml \
  --ask-vault-pass
```

Example playbook:

```yaml
---
- name: Bootstrap NetBox instance
  hosts: netbox_servers
  roles:
    - role: ansible-role-netbox-bootstrap
      vars:
        netbox_url: "https://netbox.example.com"
        netbox_api_token: "{{ vault_netbox_api_token }}"
```

### Re-running (Idempotency)

All tasks are idempotent — re-running the playbook against an already-bootstrapped
instance is safe. Objects are matched by slug (or name for objects without slugs).
Existing objects are updated if their attributes differ from the var file; objects in
NetBox that are not in the var file are left alone (no destructive cleanup).

---

## 5. Token & Secret Management

| Secret                            | Storage                  | Used by                |
|-----------------------------------|--------------------------|------------------------|
| Source NetBox API token (export)  | Env var / CLI flag only  | `export_netbox.py`     |
| Target NetBox API token (apply)   | Ansible Vault            | Ansible role           |
| Default bootstrap user password   | Ansible Vault            | Ansible role (users.yml)|
| TSIG key, other service secrets   | Ansible Vault            | Other roles            |

The export token is **never committed to disk**. The target token lives in
`group_vars/all/vault.yml` (Ansible Vault encrypted), referenced as
`vault_netbox_api_token`.

---

## 6. Dependency Ordering Notes

Some objects have hard dependencies that must be respected:

- `locations` depend on `sites` — sites must exist first.
- `aggregates` depend on `rirs` — RIRs must exist first.
- `permissions` reference `groups` by name — groups must exist first.
- `users` reference `groups` — groups must exist first.
- `custom_fields` may reference `object_types` — those are built-in and always present.
- `sites` may reference `regions`, `site_groups`, `tenants` — those must exist first.

The `tasks/main.yml` include order enforces this. Do not reorder without reviewing
dependencies.

---

## 7. Future Considerations

- **`export_netbox.py diff` subcommand** — compare a live instance against committed
  var files and report drift. Useful for detecting manual changes made outside Ansible.
- **`export_netbox.py validate` subcommand** — validate var files against the NetBox
  OpenAPI schema before running the playbook.
- **Config contexts** — `/api/extras/config-contexts/` could be added as Tier 6 once
  the structural tiers are stable.
- **Scheduled export** — a cron job or Cowork scheduled task to periodically re-export
  and open a PR if var files have drifted from the live instance.
- **Multi-instance support** — Click subcommands could support named profiles
  (`--profile production`, `--profile staging`) with URLs and token env vars stored
  in a local `~/.netbox-export.ini` (token values excluded from ini, always env-only).
