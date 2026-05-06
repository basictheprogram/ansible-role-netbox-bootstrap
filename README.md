# ansible-role-netbox-bootstrap

Idempotent bootstrap of a fresh [NetBox](https://netboxlabs.com/) instance from declarative YAML variable files. Covers users, groups, object permissions, custom fields, tags, webhooks, export templates, DCIM structure, IPAM structure, and tenancy.

A companion Python CLI (`scripts/export_netbox.py`) snapshots any live NetBox instance into the YAML variable files, giving you a repeatable "configuration as code" workflow: export once, commit, apply anywhere.

---

## Requirements

### Ansible

- Ansible >= 2.20

### Collections

Install before running the role:

```bash
ansible-galaxy collection install netbox.netbox community.general
```

| Collection          | Purpose                                                  |
|---------------------|----------------------------------------------------------|
| `netbox.netbox`     | NetBox API modules (tags, sites, device roles, etc.)     |
| `community.general` | `collection_version` lookup used in preflight checks     |

### Python (control node)

The export script requires:

```bash
cd scripts/
pip install -r requirements.txt
```

The role itself does not require any additional Python packages on the control node beyond Ansible's standard dependencies.

### NetBox

- NetBox >= 3.7
- An API token with write access to the objects you intend to bootstrap

---

## Role Variables

All variables have defaults defined in `defaults/main.yml`.

### Connection

| Variable                | Default                      | Description                                      |
|-------------------------|------------------------------|--------------------------------------------------|
| `netbox_url`            | `https://netbox.example.com` | Base URL of the target NetBox instance           |
| `netbox_api_token`      | `{{ vault_netbox_api_token }}`| API token (store in Ansible Vault)              |
| `netbox_validate_certs` | `true`                       | Validate TLS certificates                        |

### Bootstrap Password

| Variable                            | Default                                      | Description                                               |
|-------------------------------------|----------------------------------------------|-----------------------------------------------------------|
| `netbox_bootstrap_default_password` | `{{ vault_netbox_bootstrap_default_password }}`| Initial password for bootstrapped users (store in Vault) |

Users are created with this password and should change it on first login.

### Section Toggles

Each bootstrap section can be enabled or disabled independently. All sections are enabled by default.

| Variable                           | Default | Section                  |
|------------------------------------|---------|--------------------------|
| `netbox_bootstrap_groups`          | `true`  | User groups              |
| `netbox_bootstrap_users`           | `true`  | Local users              |
| `netbox_bootstrap_permissions`     | `true`  | Object permissions       |
| `netbox_bootstrap_tags`            | `true`  | Tags                     |
| `netbox_bootstrap_custom_fields`   | `true`  | Custom fields            |
| `netbox_bootstrap_custom_links`    | `true`  | Custom links             |
| `netbox_bootstrap_webhooks`        | `true`  | Webhooks                 |
| `netbox_bootstrap_export_templates`| `true`  | Export templates         |
| `netbox_bootstrap_tenant_groups`   | `true`  | Tenant groups            |
| `netbox_bootstrap_tenants`         | `true`  | Tenants                  |
| `netbox_bootstrap_regions`         | `true`  | Regions                  |
| `netbox_bootstrap_site_groups`     | `true`  | Site groups              |
| `netbox_bootstrap_sites`           | `true`  | Sites                    |
| `netbox_bootstrap_locations`       | `true`  | Locations                |
| `netbox_bootstrap_rack_roles`      | `true`  | Rack roles               |
| `netbox_bootstrap_device_roles`    | `true`  | Device roles             |
| `netbox_bootstrap_platforms`       | `true`  | Platforms                |
| `netbox_bootstrap_rirs`            | `true`  | RIRs                     |
| `netbox_bootstrap_aggregates`      | `true`  | IP aggregates            |
| `netbox_bootstrap_vrfs`            | `true`  | VRFs                     |
| `netbox_bootstrap_route_targets`   | `true`  | Route targets            |
| `netbox_bootstrap_vlan_groups`     | `true`  | VLAN groups              |

---

## Export Script

Before running the role, populate the `vars/` files by exporting from a source NetBox instance.

### Setup

```bash
cd scripts/
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your source NetBox URL and token
```

### .env

```ini
NETBOX_URL=https://netbox.corp.example.com
NETBOX_TOKEN=nbt_xxxx.<your-token>
NETBOX_OUTPUT_DIR=../vars
```

### Run

```bash
# Export all sections
python export_netbox.py

# Export specific sections only
python export_netbox.py --sections users,groups,permissions,device_roles

# Dry run — print what would be written without touching files
python export_netbox.py --dry-run --verbose

# Override any .env value at runtime
python export_netbox.py --url https://netbox.example.com --sections tags,custom_fields
```

### Configuration precedence

```
.env (script dir) → --env-file <path> → explicit CLI flags
```

Commit the resulting `vars/*.yml` to version control. These files are the source of truth for your bootstrap configuration. Do not hand-edit them — re-run the export script to update.

---

## Dependency and Application Order

Sections are applied in strict dependency order inside `tasks/main.yml`. The order matters:

1. **Preflight** — connectivity and variable checks
2. **Users & Access** — groups → users → permissions
3. **Extras** — tags → custom fields → custom links → webhooks → export templates
4. **Tenancy** — tenant groups → tenants
5. **DCIM structure** — regions → site groups → sites → locations → rack roles → device roles → platforms
6. **IPAM structure** — RIRs → aggregates → VRFs → route targets → VLAN groups

---

## Example Playbook

### Full bootstrap

```yaml
---
- name: Bootstrap NetBox instance
  hosts: localhost
  gather_facts: false
  roles:
    - role: ansible-role-netbox-bootstrap
      vars:
        netbox_url: "https://netbox.example.com"
        netbox_api_token: "{{ vault_netbox_api_token }}"
```

### Permissions and users only

```yaml
---
- name: Sync NetBox users and permissions
  hosts: localhost
  gather_facts: false
  roles:
    - role: ansible-role-netbox-bootstrap
      vars:
        netbox_url: "https://netbox.example.com"
        netbox_api_token: "{{ vault_netbox_api_token }}"
        netbox_bootstrap_tags: false
        netbox_bootstrap_custom_fields: false
        netbox_bootstrap_custom_links: false
        netbox_bootstrap_webhooks: false
        netbox_bootstrap_export_templates: false
        netbox_bootstrap_tenant_groups: false
        netbox_bootstrap_tenants: false
        netbox_bootstrap_regions: false
        netbox_bootstrap_site_groups: false
        netbox_bootstrap_sites: false
        netbox_bootstrap_locations: false
        netbox_bootstrap_rack_roles: false
        netbox_bootstrap_device_roles: false
        netbox_bootstrap_platforms: false
        netbox_bootstrap_rirs: false
        netbox_bootstrap_aggregates: false
        netbox_bootstrap_vrfs: false
        netbox_bootstrap_route_targets: false
        netbox_bootstrap_vlan_groups: false
```

### Vault setup

Store sensitive values in `group_vars/all/vault.yml` (Ansible Vault encrypted):

```yaml
vault_netbox_api_token: "nbt_xxxx.<token>"
vault_netbox_bootstrap_default_password: "ChangeMe123!"
```

Reference them in `group_vars/all/vars.yml`:

```yaml
netbox_api_token: "{{ vault_netbox_api_token }}"
netbox_bootstrap_default_password: "{{ vault_netbox_bootstrap_default_password }}"
```

Run with:

```bash
ansible-playbook bootstrap_netbox.yml --ask-vault-pass
```

---

## Re-running (Idempotency)

All tasks are idempotent. Re-running against an already-bootstrapped instance is safe. Objects are matched by slug or name. Existing objects are updated if their attributes differ from the var files; objects in NetBox that are not present in the var files are left untouched.

---

## License

MIT

---

## Author

Bob Tanner — [Real Time Enterprises, Inc.](https://www.realtime.net)
