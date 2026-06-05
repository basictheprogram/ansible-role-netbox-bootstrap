# TrueNAS CE Disk Tracking in NetBox

This document describes how to record physical disks from a TrueNAS CE appliance
in NetBox. Follow this procedure whenever a disk is added, replaced, or retired.

---

## How disks are modelled

Each physical disk is a **NetBox Inventory Item** (`dcim.inventoryitem`) attached
to the parent TrueNAS device. This keeps site-level device data (platform, role,
location) separate from per-disk operational data.

The bootstrap role provisions these custom fields on every `dcim.inventoryitem`:

| Field | Type | Notes |
|---|---|---|
| Disk Serial Number | text | Manufacturer serial — primary identifier |
| Disk Capacity (GB) | integer | Raw capacity, not formatted/usable size |
| Disk Type | text | `HDD`, `SSD`, or `NVMe` |
| Disk RPM | integer | Spindle speed; leave blank for SSD/NVMe |
| SMART Status | text | `Pass`, `Warn`, `Fail`, or `Unknown` |
| ZFS Pool | text | Pool name (e.g. `tank`, `data`); blank if spare/unassigned |
| Disk Bay / Slot | text | TrueNAS label (e.g. `da0`, `sda`, `Slot 3`) |

---

## Where to find disk info in TrueNAS CE

Open the TrueNAS CE web UI and go to **Storage → Disks**.

The table shows: device name (`da0` / `sda`), serial number, capacity, model,
and current SMART status. For pool membership go to **Storage → Pools** and
expand the pool topology.

---

## Adding a disk to NetBox

### Step 1 — Open the device

1. NetBox → **DCIM → Devices**
2. Search for the TrueNAS appliance by name or site
3. Click the device to open its detail page

### Step 2 — Add an Inventory Item

1. Click the **Add Components** dropdown button on the device detail page
2. Select **Inventory Items**
3. Fill in the core fields:

   | Field | Value |
   |---|---|
   | Device | (pre-filled — the TrueNAS appliance) |
   | Name | TrueNAS device label, e.g. `da0` or `Slot 3` |
   | Manufacturer | Disk manufacturer if known (e.g. Seagate, WD, Samsung) |
   | Part ID / Model | Model string from TrueNAS Disks table |
   | Serial Number | Serial from TrueNAS Disks table |
   | Tags | `truenas` + one of `hdd`, `ssd`, `nvme`; add `zfs` if pool-assigned |

4. Scroll to **Custom Fields** and fill in:
   - **Disk Serial Number** — repeat the serial here for API queryability
   - **Disk Capacity (GB)** — raw GB from TrueNAS (e.g. `16000` for a 16 TB drive)
   - **Disk Type** — `HDD`, `SSD`, or `NVMe`
   - **Disk RPM** — e.g. `7200`; leave blank for SSD/NVMe
   - **SMART Status** — check TrueNAS Storage → Disks → SMART column
   - **ZFS Pool** — pool name, or leave blank if spare/unassigned
   - **Disk Bay / Slot** — the TrueNAS device name (e.g. `da0`)

5. Click **Save**

### Step 3 — Repeat for each disk

Add one Inventory Item per physical disk. A typical TrueNAS appliance will have
one item per data disk, plus any hot spares or cache/log devices.

---

## Replacing a disk

1. Open the old disk's Inventory Item in NetBox
2. Update **SMART Status** to `Fail` if it has not been done already
3. Once the replacement is physically installed and showing in TrueNAS:
   - Update **Disk Serial Number**, **Disk Bay / Slot**, **Disk Type**, and
     **Disk Capacity (GB)** to match the new disk
   - Reset **SMART Status** to `Pass`
   - Update **ZFS Pool** once the resilver completes
4. Add a **Journal Entry** on the device (device detail → Journal tab) noting
   the date, failed serial, and replacement serial

---

## Retiring a disk

1. Open the Inventory Item
2. Set **SMART Status** to `Fail`
3. Clear **ZFS Pool** (disk is no longer pool-assigned)
4. Remove the `zfs` tag if present
5. Add a Journal Entry on the device noting the retirement date and reason
6. Delete the Inventory Item once the disk is physically removed from the chassis

---

## Keeping SMART status current

NetBox does not poll TrueNAS directly. Update **SMART Status** manually:

- After any TrueNAS SMART test completes
- When TrueNAS sends a SMART alert
- As part of a periodic audit (quarterly is reasonable)

A future enhancement could automate this via the TrueNAS API and a scheduled
script that PATCHes the NetBox Inventory Item custom field. See DESIGN.md §8
(Future Considerations) for context on scheduled exports.

---

## Quick reference — TrueNAS capacity vs. GB entry

TrueNAS reports disk size in decimal gigabytes (1 TB = 1000 GB, not 1024).
Enter the decimal value in **Disk Capacity (GB)**:

| Drive label | Enter |
|---|---|
| 4 TB | `4000` |
| 8 TB | `8000` |
| 16 TB | `16000` |
| 500 GB SSD | `500` |
| 1 TB NVMe | `1000` |
