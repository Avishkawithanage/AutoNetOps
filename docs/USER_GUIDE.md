# AutoNetOps — User Guide

For network administrators and operators. For installation see [README](../README.md).

## 1. Roles

| Role | Can do |
|---|---|
| **Viewer** | See devices, backup history, configuration text, diffs, jobs, reports |
| **Operator** | Everything a viewer can, plus: test connections, run backups, state snapshots, download configs, protect versions, cancel pending jobs, view audit logs. Can *request* a restore only if the approval workflow is enabled |
| **Administrator** | Everything, plus: add/edit/delete devices and groups, schedules, users, retention policy, execute/approve restores, roll back |

Permissions are enforced by the server, not only by hidden buttons.

## 2. Signing in

Open the AutoNetOps address (e.g. `http://localhost:8000`) and sign in. After 5 failed attempts the account is locked for 15 minutes (the message is always "Invalid credentials"). Change your password under **Settings → Change my password** (minimum 10 characters). **Sign out** is at the bottom of the left menu; sessions expire after 60 minutes.

## 3. Dashboard

Shows: enabled devices, reachable devices, failed connection tests, successful/failed backups today, unchanged vs. changed configs today, queued jobs, storage used, restores awaiting approval, latest successful backup and recent notifications. Red or amber numbers need attention.

## 4. Devices

### Add a device (administrator)
1. **Devices → + Add device**.
2. Fill in: **Name** (letters, digits, `_ . -`), **Management IP**, **Platform** (IOS or IOS-XE), **SSH port**, optional location and group, **SSH username/password**, optional **enable secret**.
3. Credentials are encrypted and are never shown again. Use a least-privilege account.
4. Open the device and press **Test connection**. It reports separately: port reachable, SSH login, privileged access, detected platform (a warning appears if it differs from the configured one). Fix any red item before backing up. Real devices need their SSH key in `secrets/known_hosts` (see README).

### Device page
Buttons (by role): **Test connection**, **Backup running**, **Backup startup**, **State snapshot**, **Disable/Enable**, **Delete**. A disabled device is skipped by backups and schedules. A device with stored backups cannot be deleted — disable it instead.

*State snapshot* stores `show version`, interfaces, VLANs and routes. It is operational information, separate from configuration backups.

### Groups
At the bottom of **Devices** (administrator): create groups such as *Core Network* or *Branch Offices*, assign them when adding a device, and target them from schedules.

## 5. Backups

### Manual backup
Press **Backup running** or **Backup startup** on a device. A job is queued and the page refreshes shortly. Results:

| Job status | Meaning |
|---|---|
| SUCCESS + **CHANGED** | New version stored (a change was detected; a notification is created) |
| SUCCESS + **UNCHANGED** | Same configuration as before; no duplicate version created |
| SUCCESS + **NOT_COMPARABLE** | First backup — nothing to compare with |
| FAILED / TIMEOUT | See the error code on the **Jobs** page; no version is created |

Common error codes: `AUTH_FAILED` (wrong credentials — not retried), `UNREACHABLE`/`TIMEOUT` (retried automatically with back-off), `INVALID_OUTPUT` (device returned an error or truncated text), `HOST_KEY_*` (SSH key problem), `DEVICE_BUSY` (another backup/restore running), `STORAGE_ERROR`.

Timestamps and "volatile" lines (e.g. *Last configuration change at…*) are ignored when deciding whether something changed; the raw configuration is always stored unchanged.

### Configuration history
On the device page, each row is a version: number, type, time, who/what created it, change status, size and checksum. 🔒 = protected from automatic deletion. **pre-restore** marks safety backups taken before a restore.

### Viewing and downloading
**Open** shows the read-only text with line numbers and search, plus an **Integrity** result. If the stored file no longer matches its SHA-256, reading and restoring are blocked and a critical notification is raised. Operators can **Download**.

## 6. Comparing versions

**Compare**: choose a device and config type, then a source (older) and target (newer) version and press **Compare**. You see lines added/removed, totals, heuristic categories (Interfaces, VLANs, Routing, ACLs, NAT, SNMP, NTP, AAA…), and a coloured diff. Options: *Show only changed lines*, *Ignore volatile lines*, **Copy unified diff**. Only versions of the same device and type can be compared. Categories are keyword-based, not a semantic analysis.

## 7. Schedules (administrator)

**Schedules → New schedule**:

| Frequency | Fields |
|---|---|
| hourly | minute from the time field |
| every_n_hours | number of hours |
| daily | time `HH:MM` |
| weekly | days e.g. `mon,thu` + time |
| monthly | day 1–28 + time |
| cron | standard 5-field cron |

Also choose the **IANA timezone** (e.g. `Asia/Colombo`), which config types to back up, and a target group (empty = all enabled devices). **Run now** fires a schedule immediately (running it twice in the same minute is ignored). Disabled schedules create no jobs. One job is created per device per config type; a failing device never stops the others.

## 8. Jobs

**Jobs** lists every backup job with filters (status, type: manual/scheduled/pre_restore/safety). Pending jobs can be cancelled (running SSH sessions are not interrupted). The page auto-refreshes while jobs are active.

## 9. Restore — read carefully

Restore changes a live device and can cut your access to it. Use a console/out-of-band path as a safety net and **try it in a lab first**.

### Starting a restore (administrator; operator if approval is enabled)
1. Open the version you want to return to → **Restore this version…** (only running-config versions).
2. The dialog shows: validation errors (block the restore), warnings (must be acknowledged, e.g. *management IP missing from target*), and how many lines will change.
3. Choose a mode:
   - **Merge** — replays the configuration lines. It cannot remove lines that exist only on the device, so the result is normally **NEEDS_REVIEW**.
   - **Replace** — uploads the file and runs `configure replace`. Needs SCP enabled on the device and a platform that supports it. Validate in a lab first.
4. Optionally tick **Save to startup-config** (done only after a verified success).
5. Type the device name to confirm and press **Confirm restore**.

### What happens
Re-check integrity → take a **protected pre-restore backup** (restore is aborted if this fails) → apply → reconnect and verify → record the result. Commands such as `reload` or `write erase` inside a configuration are blocked.

### Results (**Restores** page)
| Status | Meaning / what to do |
|---|---|
| SUCCESS | Device matches the target |
| NEEDS_REVIEW | Target lines present but extra lines remain (normal for merge) — review the "Extra on device" list |
| FAILED | Target lines missing or CLI errors — consider rollback |
| UNCERTAIN | Could not verify (connection lost, restart…). **Check the device manually**; do not assume either outcome |
| PENDING_APPROVAL | Waiting for a second administrator |
| REJECTED | Approver refused |

**Roll back to pre-restore backup** (administrator) starts a new restore of the saved safety backup. It is never automatic, and a rollback in merge mode has the same limitation as above.

### Approval workflow
If the server runs with `RESTORE_REQUIRES_APPROVAL=true`, every restore waits for approval; the requester cannot approve their own request. Administrators approve or reject on the **Restores** page.

## 10. Notifications and reports

- **Dashboard / Reports → Notifications**: backup failures (auth failures are *critical*), detected changes, restore results, integrity failures, storage thresholds. Use **Mark all read**.
- Optional email/webhook delivery is configured in `.env` (SMTP\_*, WEBHOOK\_URL). Notifications never contain configurations or secrets.
- **Reports**: daily backup summary (14 days) with **Export CSV**, and storage usage per device. Warning at 80 %, critical at 90 % of the configured capacity.

## 11. Audit logs (operator+)

Records logins (including failures), device changes, backup requests/results, downloads, restores, approvals, schedule runs, user changes and retention runs: who, when, device, result, source IP. Filter by action (e.g. `restore`). Entries cannot be edited or deleted through the application.

## 12. Users (administrator)

**Users**: create accounts (role + password ≥ 10 chars), change roles, disable/enable. You cannot demote or disable yourself. Resetting someone's password unlocks them.

## 13. Retention (administrator)

**Settings → Retention policy**: maximum versions per device and config type, and maximum age in days (0 = unlimited). **Preview cleanup** lists what would be deleted before **Run cleanup**. The latest version, protected versions and versions used by a restore are never deleted. Cleanup also runs nightly at 03:30 UTC.

## 14. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `HOST_KEY_UNVERIFIED` / `HOST_KEY_UNKNOWN` | Add the device key: `ssh-keyscan -p 22 <ip> >> secrets/known_hosts` (verify the fingerprint) |
| `HOST_KEY_MISMATCH` | Key changed — device replaced or possible impersonation. Investigate before updating known_hosts |
| `AUTH_FAILED` | Wrong username/password/enable secret. Edit the device credentials; not retried automatically |
| `TIMEOUT` / `UNREACHABLE` | Routing/firewall/SSH disabled; test from the AutoNetOps host with `ssh` |
| `INVALID_OUTPUT` | Account lacks privilege (needs privilege 15 or enable secret) or output truncated |
| Platform mismatch warning | Change the device's platform to the detected one |
| Integrity failure | Backup file was altered or the `ENCRYPTION_KEY` changed — restore the file from your off-host copy |
| Everything says "Invalid credentials" | Account locked (wait 15 min) or ask an administrator to reset your password |
| "Mock" device in demos | `DRIVER_MODE=mock` in `.env` simulates devices; switch to `cisco` for real ones |

## 15. Good practice

- Use dedicated, least-privilege device accounts and rotate them.
- Back up AutoNetOps itself (database + `backup_storage`) and keep `ENCRYPTION_KEY` separately.
- Protect (🔒) known-good versions such as "golden" configs.
- Never test restores on production first; keep out-of-band access ready.
- Serve AutoNetOps over HTTPS and restrict network access to the device management network.
