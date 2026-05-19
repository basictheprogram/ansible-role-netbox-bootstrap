# ansible-role-netbox-bootstrap

Idempotent bootstrap of a fresh [NetBox](https://netboxlabs.com/) instance from declarative YAML variable files. Covers users, groups, object permissions, custom fields, tags, webhooks, export templates, DCIM structure, IPAM structure, tenancy, and cloud inventory (AWS managed services).

Two companion export scripts snapshot configuration into the YAML variable files, giving you a repeatable "configuration as code" workflow: export once, commit, apply anywhere.

- `scripts/export_netbox.py` — snapshot a live NetBox instance into `vars/`
- `scripts/export_aws_ec2.py` — populate EC2 instance types into `vars/virtual_machine_types.yml`
- `scripts/export_aws_rds.py` — populate RDS DB instances into `vars/rds_instances.yml`

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

The export scripts require:

```bash
cd scripts/
pip install -r requirements.txt
```

The role itself does not require any additional Python packages on the control node beyond Ansible's standard dependencies.

### NetBox

- NetBox >= 4.0 for all structural sections
- NetBox >= 4.6 for `virtual_machine_types` (`VirtualMachineType` was added in 4.6.0)
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

| Variable                            | Default                                        | Description                                               |
|-------------------------------------|------------------------------------------------|-----------------------------------------------------------|
| `netbox_bootstrap_default_password` | `{{ vault_netbox_bootstrap_default_password }}`| Initial password for bootstrapped users (store in Vault) |

Users are created with this password and should change it on first login.

### Cloud Inventory

| Variable              | Default    | Description                                                              |
|-----------------------|------------|--------------------------------------------------------------------------|
| `netbox_rds_cluster`  | `AWS RDS`  | NetBox cluster name to assign RDS instances to. Override per environment.|

The cluster and cluster type are defined in `vars/clusters.yml` and `vars/cluster_types.yml`. Override `netbox_rds_cluster` in your playbook vars when running a per-region export (e.g. `AWS RDS us-east-1`).

### Section Toggles

Each bootstrap section can be enabled or disabled independently. All sections are enabled by default.

#### Tier 1 — Users & Access

| Variable                       | Default | Section            |
|--------------------------------|---------|--------------------|
| `netbox_bootstrap_groups`      | `true`  | User groups        |
| `netbox_bootstrap_users`       | `true`  | Local users        |
| `netbox_bootstrap_permissions` | `true`  | Object permissions |

#### Tier 2 — Extras

| Variable                            | Default | Section          |
|-------------------------------------|---------|------------------|
| `netbox_bootstrap_tags`             | `true`  | Tags             |
| `netbox_bootstrap_custom_fields`    | `true`  | Custom fields    |
| `netbox_bootstrap_custom_links`     | `true`  | Custom links     |
| `netbox_bootstrap_webhooks`         | `true`  | Webhooks         |
| `netbox_bootstrap_export_templates` | `true`  | Export templates |

#### Tier 3 — Tenancy

| Variable                          | Default | Section        |
|-----------------------------------|---------|----------------|
| `netbox_bootstrap_tenant_groups`  | `true`  | Tenant groups  |
| `netbox_bootstrap_tenants`        | `true`  | Tenants        |
| `netbox_bootstrap_contact_groups` | `true`  | Contact groups |
| `netbox_bootstrap_contact_roles`  | `true`  | Contact roles  |
| `netbox_bootstrap_contacts`       | `true`  | Contacts       |

#### Tier 4 — DCIM Structure

| Variable                         | Default | Section       |
|----------------------------------|---------|---------------|
| `netbox_bootstrap_regions`       | `true`  | Regions       |
| `netbox_bootstrap_site_groups`   | `true`  | Site groups   |
| `netbox_bootstrap_sites`         | `true`  | Sites         |
| `netbox_bootstrap_locations`     | `true`  | Locations     |
| `netbox_bootstrap_rack_roles`    | `true`  | Rack roles    |
| `netbox_bootstrap_device_roles`  | `true`  | Device roles  |
| `netbox_bootstrap_platforms`     | `true`  | Platforms     |

#### Tier 5 — IPAM Structure

| Variable                          | Default | Section       |
|-----------------------------------|---------|---------------|
| `netbox_bootstrap_ipam_roles`     | `true`  | IPAM roles    |
| `netbox_bootstrap_rirs`           | `true`  | RIRs          |
| `netbox_bootstrap_aggregates`     | `true`  | IP aggregates |
| `netbox_bootstrap_vrfs`           | `true`  | VRFs          |
| `netbox_bootstrap_route_targets`  | `true`  | Route targets |
| `netbox_bootstrap_vlan_groups`    | `true`  | VLAN groups   |

#### Tier 6 — Virtualization *(requires NetBox >= 4.6 for virtual_machine_types)*

| Variable                                | Default | Section                                          |
|-----------------------------------------|---------|--------------------------------------------------|
| `netbox_bootstrap_virtual_machine_types`| `true`  | VM types (EC2 families + AWS service categories) |
| `netbox_bootstrap_cluster_types`        | `true`  | Cluster types (e.g. Cloud)                       |
| `netbox_bootstrap_clusters`             | `true`  | Clusters (e.g. AWS RDS, AWS ELB)                 |

#### Tier 7 — Cloud Inventory

| Variable                         | Default | Section                                         |
|----------------------------------|---------|-------------------------------------------------|
| `netbox_bootstrap_rds_instances` | `true`  | AWS RDS DB instances as NetBox virtual machines |

---

## Export Scripts

All three scripts live in `scripts/` and share the same `.env` file. Install dependencies once:

```bash
cd scripts/
pip install -r requirements.txt
cp .env.example .env
# Edit .env — see .env.example for all variables
```

Configuration precedence for every script (last wins):

```
.env (scripts/ directory) → --env-file <path> → explicit CLI flags
```

### export_netbox.py — NetBox structural config

Snapshots a live NetBox instance into `vars/`. Run this to capture your source-of-truth NetBox configuration before bootstrapping a new instance.

```bash
# Boilerplate sections only (default)
python export_netbox.py

# Everything including site-specific data
python export_netbox.py --sections all

# Specific sections
python export_netbox.py --sections groups,permissions,device_roles

# Dry run
python export_netbox.py --dry-run --verbose
```

Required `.env` variables:

```ini
NETBOX_URL=https://netbox.corp.example.com
NETBOX_TOKEN=nbt_xxxx.<your-token>
```

### export_aws_ec2.py — EC2 instance types

Populates `vars/virtual_machine_types.yml` with EC2 instance type definitions (vcpus, memory, architecture). Defaults to the `t` and `m` families.

```bash
python export_aws_ec2.py --region us-east-1
python export_aws_ec2.py --region us-east-1 --families t,m,c --current-gen-only
python export_aws_ec2.py --region us-east-1 --dry-run --verbose
```

Credentials are resolved via the standard AWS credential chain (`~/.aws`, environment variables, instance profile). Pass `--profile` to select a named profile.

### export_aws_rds.py — RDS DB instances

Populates `vars/rds_instances.yml` with running RDS DB instances. These are pushed to NetBox as virtual machines under the `AWS RDS` cluster (Tier 7).

```bash
python export_aws_rds.py --region us-east-1
python export_aws_rds.py --region us-east-1 --engines postgres,mysql
python export_aws_rds.py --region us-east-1 --status available
python export_aws_rds.py --region us-east-1 --dry-run --verbose
```

Commit the resulting `vars/*.yml` to version control. These files are the source of truth for your bootstrap configuration. Do not hand-edit them — re-run the export script to update.

---

## Dependency and Application Order

Sections are applied in strict dependency order inside `tasks/main.yml`. The order matters:

1. **Preflight** — connectivity and variable checks
2. **Users & Access** — groups → users → permissions
3. **Extras** — tags → custom fields → custom links → webhooks → export templates
4. **Tenancy** — tenant groups → tenants → contact groups → contact roles → contacts
5. **DCIM structure** — regions → site groups → sites → locations → rack roles → device roles → platforms
6. **IPAM structure** — IPAM roles → RIRs → aggregates → VRFs → route targets → VLAN groups
7. **Virtualization** — virtual machine types → cluster types → clusters
8. **Cloud Inventory** — RDS instances (requires clusters from step 7)

---

## AWS Cloud Inventory

The role tracks AWS managed services as NetBox virtual machines for invoice reconciliation. The pattern is:

- **Tenant** → AWS account
- **Site** → AWS region (`us-east-1`, `eu-west-1`, etc.)
- **VirtualMachineType** → service tier (`Application Load Balancer`, `EFS Standard`, etc.)
- **Cluster** → service family (`AWS RDS`, `AWS ELB`, `AWS EFS`, `AWS Route53`, `AWS SES`)
- **Virtual Machine** → each individual service instance

`vars/virtual_machine_types.yml` includes type definitions for all common AWS service tiers out of the box. `vars/clusters.yml` defines one cluster per service family under the `Cloud` cluster type.

To add a new AWS service family, add its type entries to `vars/virtual_machine_types.yml`, add its cluster to `vars/clusters.yml`, write an export script following the `export_aws_rds.py` pattern, and add a task file and toggle following the `rds_instances` pattern.

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

### Structural config only (skip cloud inventory)

```yaml
---
- name: Bootstrap NetBox — structural config only
  hosts: localhost
  gather_facts: false
  roles:
    - role: ansible-role-netbox-bootstrap
      vars:
        netbox_url: "https://netbox.example.com"
        netbox_api_token: "{{ vault_netbox_api_token }}"
        netbox_bootstrap_virtual_machine_types: false
        netbox_bootstrap_cluster_types: false
        netbox_bootstrap_clusters: false
        netbox_bootstrap_rds_instances: false
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
