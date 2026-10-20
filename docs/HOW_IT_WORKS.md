# How AutoNetOps Works

A plain-language explanation of the system. For step-by-step usage see [USER_GUIDE.md](USER_GUIDE.md).

## What problem it solves

Network devices (Cisco routers and switches) keep their settings in a *configuration*. If someone changes it by mistake,
or a device fails, you need to know **what changed, who changed it, and how to get the old settings back**.
Doing this by hand on many devices is slow and error-prone. AutoNetOps does it automatically.

## The big picture

```
 You (browser)
     |
     v
 Dashboard (React)  ---HTTPS--->  API server (FastAPI)
                                       |
         +-----------------------------+------------------------------+
         |                |                 |                         |
    Login & roles    Job queue          Scheduler               Database
    (who may do      (runs backups      (starts backups         (devices, versions,
     what)            and restores,      at set times)           jobs, audit log)
                      one per device)
                           |
                           v
                   Device driver (SSH)  --->  Cisco router / switch
                           |
                           v
                  Encrypted backup files
```

## The main parts

| Part | What it does |
|---|---|
| **Dashboard** | The web pages you click: devices, history, compare, schedules, restore |
| **API server** | Receives requests, checks who you are and your role, starts the right action |
| **Device driver** | The only part that talks to devices over SSH. A *mock* driver pretends to be a device for demos and tests |
| **Job queue** | Runs backups/restores in the background, a limited number at once, never two operations on the same device together |
| **Scheduler** | Creates backup jobs automatically (e.g. every night at 02:00 in your timezone) |
| **Database** | Stores devices, encrypted credentials, version records, jobs, users, audit log |
| **Backup storage** | Configuration files, encrypted on disk |

## What happens during a backup

1. A job is created (by you, or by a schedule).
2. The system connects to the device over SSH and runs `show running-config` (or `show startup-config`).
3. It **checks the output is a real configuration** (not an error or a cut-off message).
4. It calculates a **SHA-256 checksum** (a fingerprint of the content).
5. It compares with the last version, ignoring lines that change by themselves (like timestamps).
6. **Unchanged** → no new version, job still marked successful. **Changed** → a new version is saved and a notification is raised.
7. The result is written to the job history and the audit log. A failing device never stops the other devices.

## What happens during a restore

Restore is the risky part, so it has several safety steps:

1. **Check** the chosen version: checksum still matches, same device, looks complete, contains no dangerous commands (like `reload`).
2. **Warn** about risks (for example: "this config does not contain the device's management IP — you may lose access").
3. **Pre-restore backup**: save the device's current config first (protected from deletion). If this fails, the restore is cancelled.
4. **Confirm**: you type the device name. In strict setups a second administrator must approve.
5. **Apply** the old configuration.
6. **Verify**: read the device again and compare with what was intended.
7. **Result**: SUCCESS, NEEDS_REVIEW, FAILED, or UNCERTAIN (if the connection was lost and the state cannot be proven).
8. **Rollback** (manual, administrator): restore the pre-restore backup.

## How it stays secure

- **Logins** with roles: viewer (read), operator (backups), administrator (everything). Checked on the server, not just hidden buttons.
- **Account lock** after 5 wrong passwords.
- **Device passwords and backup files are encrypted**; the key is kept outside the database.
- **SSH host keys are verified**, protecting against fake devices.
- **Audit log** records who did what, when, on which device, and the result.
- **Integrity check**: if a stored backup was modified, it cannot be viewed or restored, and an alert is raised.

## Two modes

| Mode | Use it for |
|---|---|
| **mock** (`DRIVER_MODE=mock`) | Trying the system, demos, automatic tests — no real device needed |
| **cisco** (`DRIVER_MODE=cisco`) | Real devices over SSH. Test in a lab first |

## What it does *not* do (yet)

Real-time change alerts (changes are found when a backup runs), device auto-discovery, selective restore of single
sections, other vendors (only Cisco IOS / IOS-XE), multi-factor login. Restore has not been tested on real Cisco
hardware — validate it in an EVE-NG / GNS3 lab first.

## Where things are in the code

```
backend/app/api/        web endpoints (devices, backups, restores, schedules ...)
backend/app/services/   the logic: backup, restore, diff, scheduler, retention
backend/app/network/    SSH drivers (Cisco + mock) and the CLI commands
backend/app/security/   passwords, tokens, encryption
frontend/src/pages/     dashboard pages
tests/                  automatic tests
```
