# AutoNetOps
## Automated Network Configuration & Backup System

**Project type:** Network Automation / NetDevOps  
**Primary purpose:** Automate Cisco configuration backups, scheduled backups, configuration comparison, change detection, and controlled restoration.

---

## 1. Project Overview

AutoNetOps is a web-based platform that helps network administrators manage Cisco device configurations centrally. Instead of manually connecting to each router or switch, copying configuration output, comparing files, and restoring old settings, administrators can use AutoNetOps to automate these tasks.

### Main objectives

- Manage Cisco network devices from one dashboard.
- Connect to devices securely using SSH.
- Back up running and startup configurations.
- Run backups manually or on a schedule.
- Maintain versioned configuration history.
- Detect changes between backups.
- Compare configuration versions visually.
- Restore a selected configuration with safety checks.
- Verify restore results and support recovery procedures.
- Record important actions in audit logs.
- Notify administrators about failures and important changes.

### Main workflow

```text
Cisco Router / Switch
        |
        | SSH
        v
AutoNetOps Network Automation Layer
        |
        +--> Collect configuration
        +--> Validate output
        +--> Calculate SHA-256 checksum
        +--> Compare with previous version
        +--> Store configuration/version
        +--> Record job and audit results
                     |
                     v
             Database + Backup Storage
                     |
                     v
               Web Dashboard
          History / Diff / Restore / Jobs
```

---

## 2. Main Features

1. **Device Management** — Add, edit, test, group, disable, and remove devices.
2. **Manual Backup** — Start a backup whenever an authorized user needs one.
3. **Scheduled Backup** — Run backups hourly, daily, weekly, or on supported custom schedules.
4. **Running Configuration Backup** — Collect the active configuration.
5. **Startup Configuration Backup** — Collect the saved configuration used during startup.
6. **Versioning** — Keep a history of successful, distinct configuration versions.
7. **Duplicate Detection** — Use a checksum to detect unchanged configurations.
8. **Configuration Diff** — Show added and removed lines between versions.
9. **Change Detection** — Identify configuration changes since the last successful version.
10. **Restore** — Apply a selected historical configuration after validation and confirmation.
11. **Pre-Restore Backup** — Save the current configuration before a restore.
12. **Restore Verification** — Re-collect configuration and compare it with the target.
13. **Recovery/Rollback Support** — Provide a controlled recovery process if restoration fails.
14. **Job Queue** — Limit concurrency and handle many devices safely.
15. **Failure Handling** — Handle timeouts, unreachable devices, authentication failures, and partial failures.
16. **Audit Logs** — Record who performed an action, when, on which device, and with what result.
17. **Role-Based Access Control (RBAC)** — Restrict sensitive operations according to user role.
18. **Notifications** — Send alerts for failures, detected changes, restore results, and storage warnings.
19. **Retention Management** — Remove eligible old versions according to a policy while protecting important versions.
20. **Reports and Dashboard** — Summarize devices, jobs, failures, configuration changes, and storage usage.
21. **Device Groups** — Organize devices by site, role, or network layer.
22. **State Snapshots** — Optionally collect operational information such as software version, interface status, VLANs, and routes. These are separate from configuration backups.

---

## 3. Recommended Technology Stack

| Component | Recommended technology | Purpose |
|---|---|---|
| Frontend | React | Web dashboard |
| Backend | Python + FastAPI | REST API and business logic |
| Cisco automation | Netmiko | SSH-based CLI automation |
| Optional network abstraction | NAPALM | Normalized operations for supported platforms |
| Database | PostgreSQL | Devices, users, versions, schedules, jobs, and audit data |
| Job queue | Celery + Redis | Background jobs and controlled concurrency |
| Scheduler | Celery Beat or APScheduler | Trigger scheduled backups |
| Configuration storage | Protected filesystem or object storage | Store configuration files |
| Diff engine | Python `difflib` initially | Compare text configurations |
| Authentication | Secure sessions or JWT | Authenticate API requests |
| Password hashing | Argon2id or bcrypt | Store user password hashes |
| Deployment | Docker Compose | Run application services |
| Lab environment | EVE-NG or GNS3 | Test against authorized virtual network devices |
| Version control | Git | Track source code |

For a small prototype, start with FastAPI, Netmiko, PostgreSQL, local protected storage, and APScheduler. Add Redis/Celery when background job volume or concurrency requires it.

---

## 4. System Architecture

```text
                         User
                          |
                          v
                  React Web Dashboard
                          |
                        HTTPS
                          |
                          v
                    FastAPI REST API
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
   Authentication    Device Manager     Scheduler
          |               |                |
          |               v                v
          |          Cisco Driver       Job Queue
          |               |                |
          |               +--------+-------+
          |                        |
          v                        v
      PostgreSQL              Cisco Devices
          ^                        |
          |                        |
          +----------+-------------+
                     |
              Backup / Diff /
              Restore Services
                     |
              Protected Storage
                     |
                 Audit Logs
```

Keep the API layer, business services, network drivers, and storage logic separate. API routes should not contain all SSH and backup logic directly.

---

## 5. Device Management

### 5.1 Device fields

- Device name
- Hostname
- Management IP address
- Vendor
- Platform/operating system
- SSH port
- Location/site
- Device group
- Description
- Credential reference
- Enabled/disabled status
- Created and updated timestamps

Example:

```text
Device Name: CORE-R1
Management IP: 192.0.2.10
Vendor: Cisco
Platform: IOS-XE
SSH Port: 22
Location: Main Site
Group: Core Network
```

Use documentation-only IP addresses in examples. In a real lab, use the actual management IP addresses assigned to devices you are authorized to administer.

### 5.2 Add-device workflow

1. Validate the submitted name, IP address, port, and platform.
2. Store credentials securely or store a reference to a secrets manager.
3. Test reachability and SSH connectivity.
4. Authenticate and identify the device platform.
5. Record the connection test result.
6. Enable the device for backup only after it is configured correctly.

### 5.3 Connection test

A connection test should report separate results for:

- Network reachability (if tested)
- TCP/SSH availability
- SSH authentication
- Privileged-mode access, if required
- Platform identification
- Last test time and error details

A ping response alone does not prove that SSH or authentication works.

### 5.4 Device discovery (optional)

An administrator may supply an authorized network range for discovery. Discovery should be limited to approved ranges and rate-limited. A discovered IP must not be assumed to be a Cisco device until platform identification succeeds.

### 5.5 Device groups

Example groups:

- Core Network
- Distribution
- Access Switches
- Data Center
- Branch Offices

Schedules can target a group instead of selecting each device individually.

---

## 6. Cisco Connection and Command Handling

Use SSH, validate host keys where practical, set connection/read timeouts, and close sessions reliably. Do not disable SSH host-key checks without a documented reason and compensating controls.

Centralize supported commands and platform-specific behavior in a driver layer. Do not scatter CLI strings throughout API routes.

### Initial platform support

- Cisco IOS
- Cisco IOS-XE

Add NX-OS, ASA, or other vendors only after implementing and testing platform-specific behavior.

### Common collection commands

| Purpose | Example command | Notes |
|---|---|---|
| Running configuration | `show running-config` | Active configuration |
| Startup configuration | `show startup-config` | Saved startup configuration |
| Software/platform details | `show version` | State snapshot |
| Interface summary | `show ip interface brief` | State snapshot |
| VLAN summary | `show vlan brief` | Platform-dependent state snapshot |
| Routing table | `show ip route` | State snapshot; may contain sensitive topology information |

Operational outputs such as routes and interface status should be stored separately from configuration versions. They are not substitutes for configuration backups.

### Connection lifecycle

```text
Validate device
    -> Open SSH session
    -> Authenticate
    -> Enter privileged mode if required
    -> Run approved read-only commands
    -> Collect complete output
    -> Validate output
    -> Close session
    -> Record result
```

---

## 7. Backup Engine

The backup engine is the core component.

### 7.1 Backup workflow

```text
Create backup job
    -> Check device is enabled
    -> Connect over SSH
    -> Collect requested configuration
    -> Validate output is complete and plausible
    -> Normalize only safe, documented differences
    -> Calculate SHA-256 checksum
    -> Compare with previous successful version
    -> Store a new version if changed or explicitly requested
    -> Record job status and metadata
    -> Write audit event
    -> Notify if needed
```

### 7.2 Backup types

- **Manual:** Started by an authorized user.
- **Scheduled:** Started by a schedule.
- **Pre-restore:** Created immediately before a restore attempt.
- **On-demand safety backup:** Created before a potentially disruptive maintenance operation.

Each job should identify its type, requesting user or schedule, start/end time, status, retry count, and error details.

### 7.3 Output validation

Do not treat every non-empty SSH response as a valid backup. Validation should check for common CLI errors, incomplete output, unexpected prompts, permission problems, and obvious truncation. Platform-specific checks are preferable to a single universal text rule.

### 7.4 Backup statuses

Recommended job states:

- `PENDING`
- `RUNNING`
- `SUCCESS`
- `FAILED`
- `TIMEOUT`
- `CANCELLED`

Record configuration state separately:

- `CHANGED`
- `UNCHANGED`
- `NOT_COMPARABLE`

An unchanged configuration can still be a successful backup job.

---

## 8. Configuration Versioning and Storage

Store each distinct configuration as a version with metadata. Keep job history even when no new version is created.

### Example directory structure

```text
backups/
  CORE-R1/
    2026/
      10/
        CORE-R1_2026-10-18T020000Z_v001.cfg
        CORE-R1_2026-10-19T020000Z_v002.cfg
  SW-01/
    2026/
      10/
        SW-01_2026-10-18T020000Z_v001.cfg
```

Use UTC timestamps internally and show local time in the UI. Generate paths from validated internal device IDs, not directly from user-supplied filenames.

### Version metadata

- Configuration ID
- Device ID
- Version number
- Configuration type (running/startup)
- Creation timestamp
- File/object-storage reference
- SHA-256 checksum
- File size
- Backup job ID
- Created by (user or scheduler)
- Change status
- Retention/protection status

### Duplicate detection

Calculate SHA-256 over the exact stored content or a documented canonical representation.

- Same checksum: configuration is unchanged relative to that comparison.
- Different checksum: content changed; create a new version.
- Failed or incomplete collection: do not treat it as a valid version.

Do not silently normalize meaningful configuration differences. If normalization is used to ignore timestamps or other volatile lines, retain the raw collected configuration and document the normalization rules.

### Integrity checking

When a backup is read or restored, recompute its checksum and compare it with the stored checksum. If it does not match, block restore and alert an administrator.

---

## 9. Scheduled Backups

### 9.1 Schedule options

- Hourly
- Every configured number of hours
- Daily at a selected time
- Weekly on selected days
- Monthly on a selected date
- Advanced cron-style schedules, if supported safely

Example:

```text
Schedule: Daily Cisco Backup
Target: All enabled Cisco devices
Frequency: Daily
Time: 02:00
Timezone: Asia/Colombo
Enabled: Yes
```

Store the timezone explicitly. Define what happens during daylight-saving transitions if the system is deployed in a timezone that uses them.

### 9.2 Scheduler workflow

```text
Scheduler reaches due time
    -> Find enabled schedule
    -> Resolve target devices
    -> Create one job per device
    -> Enqueue jobs
    -> Workers process jobs within concurrency limits
    -> Save results
    -> Produce summary report
```

### 9.3 Job queue and concurrency

Avoid opening an unlimited number of SSH sessions at once. Configure:

- Maximum concurrent device connections
- Per-device lock to prevent conflicting backup/restore operations
- Connection and command timeouts
- Retry policy
- Queue priority, if needed
- Job cancellation rules
- Worker health checks

Do not run a restore concurrently with a backup or another restore on the same device unless the operation model explicitly supports it.

### 9.4 Retry policy

Retry transient failures such as network timeouts with bounded exponential backoff. Do not repeatedly retry invalid credentials. Record each attempt and the final outcome.

---

## 10. Configuration Comparison (Diff)

### 10.1 Basic comparison

Allow a user to select two versions from the same device and configuration type.

Example:

```diff
 interface GigabitEthernet0/0
- ip address 192.0.2.1 255.255.255.0
+ ip address 192.0.2.10 255.255.255.0
  no shutdown
```

The interface should show:

- Source version
- Target version
- Creation timestamps
- Lines added
- Lines removed
- Total change counts
- Downloadable diff, if authorized

### 10.2 Diff implementation

Start with Python's `difflib` for line-based comparison. A later enhancement can parse configurations into sections and classify changes.

Potential categories:

- Interfaces
- VLANs
- Routing
- ACLs
- NAT
- Hostname
- SNMP
- NTP
- AAA and users

Category classification is platform-specific and should be tested. Do not claim semantic understanding if the implementation only compares lines.

### 10.3 Change detection

After a successful collection:

1. Compare the new checksum with the last successful comparable version.
2. If the checksum differs, create a new version.
3. Generate a diff.
4. Record the detected change and its time.
5. Notify configured recipients if the policy requires it.

A scheduled backup detects changes only when it next collects the configuration. It is not continuous real-time monitoring unless a separate change-event mechanism is implemented.

---

## 11. Restore System

Restore is the most sensitive feature because an incorrect configuration can disconnect a device or disrupt a network.

### 11.1 Restore workflow

```text
Select device and historical version
    -> Verify user permission
    -> Verify version checksum
    -> Confirm platform compatibility
    -> Display target configuration and diff
    -> Validate target configuration as far as possible
    -> Create and verify pre-restore backup
    -> Obtain explicit confirmation/approval
    -> Apply using the platform-specific restore procedure
    -> Verify resulting running configuration
    -> Save startup configuration only according to policy
    -> Record result and audit event
    -> If verification fails, initiate the approved recovery procedure
```

### 11.2 Restore modes

- **Full restore:** Intended to replace the configuration according to the platform-specific procedure.
- **Selective restore (advanced):** Apply selected configuration sections, such as interfaces or routing.

Implement full restore for the initial version only after validating the method on the exact Cisco platform in a lab. Selective restore is harder than removing or adding lines because configuration commands have dependencies and ordering requirements.

### 11.3 Pre-restore safety backup

Before any restore:

1. Collect the current running configuration.
2. Validate and store it as a protected pre-restore version.
3. Verify its checksum and retrievability.
4. Abort restore if the safety backup cannot be created and policy requires it.

### 11.4 Restore validation

Check, where possible:

- Backup checksum and integrity
- Target device platform compatibility
- Configuration size and completeness
- Required configuration sections
- Known unsupported or dangerous commands
- Connection and privilege requirements
- Potential management-interface or routing changes

Text validation cannot guarantee that a configuration is operationally safe. Test restores in an isolated lab first.

### 11.5 Verification

After applying the target:

1. Re-collect the running configuration.
2. Compare it with the intended target using documented normalization rules.
3. Check device connectivity and essential management access.
4. Report `SUCCESS`, `FAILED`, or `NEEDS_REVIEW`.
5. Record differences and the reason for any verification failure.

Some platforms rewrite or reorder configuration text, so exact byte-for-byte equality may not be a valid success criterion.

### 11.6 Rollback and recovery

A pre-restore backup does not automatically guarantee rollback. If a restore fails, the device might be unreachable or the session might be lost. Recovery must be platform-specific and tested. The system should mark uncertain outcomes clearly and must not blindly assume that a restore succeeded or failed.

### 11.7 Restore confirmation screen

```text
WARNING: This operation changes a network device.

Device: CORE-R1
Current version: v021
Target version: v015
Pre-restore backup: Required

Review the diff and confirm that you have a recovery plan.

[Cancel] [Confirm Restore]
```

For production environments, consider MFA or a second-person approval for restore operations.

---

## 12. Database Design

Recommended tables:

### `users`

- `id`
- `username`
- `password_hash`
- `role`
- `is_active`
- `created_at`
- `last_login_at`

### `devices`

- `id`
- `name`
- `hostname`
- `ip_address`
- `vendor`
- `platform`
- `ssh_port`
- `location`
- `group_id`
- `credential_ref`
- `is_enabled`
- `created_at`
- `updated_at`

### `credentials` (or secret references)

- `id`
- `device_id`
- `secret_reference` or encrypted credential fields
- `updated_at`

Prefer a secrets manager. If the prototype stores encrypted credentials, the encryption key must be stored separately from the database and source code.

### `configurations`

- `id`
- `device_id`
- `version_number`
- `config_type`
- `storage_key`
- `checksum_sha256`
- `size_bytes`
- `backup_job_id`
- `created_at`
- `created_by`
- `change_status`
- `is_protected`

### `backup_jobs`

- `id`
- `device_id`
- `schedule_id`
- `job_type`
- `status`
- `started_at`
- `completed_at`
- `retry_count`
- `error_code`
- `error_message`
- `configuration_id`

### `schedules`

- `id`
- `name`
- `frequency`
- `schedule_expression`
- `timezone`
- `enabled`
- `target_group_id`
- `created_by`
- `created_at`

### `restore_jobs`

- `id`
- `device_id`
- `target_configuration_id`
- `pre_restore_configuration_id`
- `status`
- `started_at`
- `completed_at`
- `performed_by`
- `approved_by`
- `verification_result`
- `recovery_status`
- `error_message`

### `audit_logs`

- `id`
- `user_id`
- `action`
- `device_id`
- `details`
- `source_ip`
- `timestamp`
- `result`

### Additional tables (as needed)

- `device_groups`
- `notifications`
- `state_snapshots`
- `restore_approvals`
- `retention_policies`

Use foreign keys, indexes, unique constraints, and database migrations. Ensure version numbers are unique per device and configuration type.

---

## 13. REST API Design

Use a consistent prefix such as `/api/v1`.

### Authentication

```http
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

### Devices

```http
GET    /api/v1/devices
POST   /api/v1/devices
GET    /api/v1/devices/{device_id}
PUT    /api/v1/devices/{device_id}
DELETE /api/v1/devices/{device_id}
POST   /api/v1/devices/{device_id}/test-connection
POST   /api/v1/devices/{device_id}/backup
GET    /api/v1/devices/{device_id}/backups
```

### Configurations and comparison

```http
GET  /api/v1/configurations/{configuration_id}
GET  /api/v1/configurations/{configuration_id}/download
GET  /api/v1/configurations/{configuration_id}/integrity
GET  /api/v1/compare?source_id=10&target_id=15
```

### Jobs

```http
GET  /api/v1/jobs
GET  /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
```

### Restore

```http
POST /api/v1/configurations/{configuration_id}/restore
GET  /api/v1/restores
GET  /api/v1/restores/{restore_id}
POST /api/v1/restores/{restore_id}/approve
```

### Schedules

```http
GET    /api/v1/schedules
POST   /api/v1/schedules
GET    /api/v1/schedules/{schedule_id}
PUT    /api/v1/schedules/{schedule_id}
DELETE /api/v1/schedules/{schedule_id}
```

### Reports and audit

```http
GET /api/v1/reports/daily-backups
GET /api/v1/reports/storage
GET /api/v1/audit-logs
```

Long-running operations should return a job ID rather than keeping an HTTP request open until the device operation finishes. Protect every endpoint with authentication and role-based authorization.

---

## 14. Backend Folder Structure

```text
autonetops/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── devices.py
│   │   │   ├── backups.py
│   │   │   ├── configurations.py
│   │   │   ├── restores.py
│   │   │   ├── schedules.py
│   │   │   ├── jobs.py
│   │   │   └── reports.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── device_service.py
│   │   │   ├── backup_service.py
│   │   │   ├── diff_service.py
│   │   │   ├── restore_service.py
│   │   │   ├── scheduler_service.py
│   │   │   └── notification_service.py
│   │   ├── network/
│   │   │   ├── base_driver.py
│   │   │   ├── cisco_ios.py
│   │   │   ├── connection.py
│   │   │   └── commands.py
│   │   ├── security/
│   │   ├── workers/
│   │   ├── db/
│   │   └── utils/
│   └── requirements.txt
├── frontend/
├── backup_storage/
├── logs/
├── tests/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## 15. Core Service Responsibilities

### `DeviceService`

- Validate and register devices.
- Update device metadata.
- Test connectivity.
- Manage device groups and enabled status.

### `BackupService`

- Open device connection through the driver.
- Collect running/startup configuration.
- Validate output.
- Calculate checksum.
- Create a version when required.
- Record job and audit results.

### `DiffService`

- Load two authorized versions.
- Verify file integrity.
- Apply documented normalization if configured.
- Generate line-based diff.
- Optionally classify changes.

### `SchedulerService`

- Create and update schedules.
- Resolve target devices.
- Enqueue due backup jobs.
- Avoid duplicate jobs for the same schedule run.

### `RestoreService`

- Validate target version and permissions.
- Create a pre-restore backup.
- Enforce confirmation/approval.
- Execute the platform-specific restore.
- Verify the result and coordinate recovery if needed.

### `NotificationService`

- Send configured email or messaging alerts.
- Avoid sending secrets or full sensitive configurations in notifications.
- Record delivery outcomes.

---

## 16. Dashboard Pages

Recommended pages:

```text
/login
/dashboard
/devices
/devices/:deviceId
/backups
/backups/:configurationId
/compare
/restores
/schedules
/jobs
/audit-logs
/reports
/users
/settings
```

### Dashboard summary cards

- Total enabled devices
- Reachable devices
- Devices with failed connection tests
- Successful backups today
- Failed backups today
- Unchanged configurations
- Configuration changes detected
- Latest successful backup
- Backup storage used

### Device details page

Show:

- Device identity and platform
- Connection test status
- Last successful backup
- Latest configuration version
- Backup history
- Change timeline
- Actions allowed for the current user's role

### Configuration viewer

Support:

- Read-only display
- Search
- Line numbers
- Copy/download with permission checks
- Compare versions
- Restore action only for authorized roles

### Job history

Filter by device, date, status, job type, and schedule. Show start/end times, retries, and a safe error summary.

---

## 17. Authentication and Authorization

Suggested roles:

| Role | Permissions |
|---|---|
| Administrator | Manage users/devices/settings; run backups; approve and execute restores |
| Network Operator | View devices; run backups; compare configurations; request restore if enabled |
| Viewer | View permitted devices, backup history, and diffs |

Enforce permissions on the backend, not only by hiding frontend buttons.

Security requirements:

- Hash user passwords with Argon2id or bcrypt.
- Use secure, expiring sessions or short-lived access tokens.
- Apply login rate limiting and temporary lockout policy.
- Validate all inputs.
- Use HTTPS.
- Protect against CSRF if cookie-based sessions are used.
- Restrict CORS to known frontend origins.
- Avoid exposing internal exception traces to clients.
- Record security-relevant events in audit logs.
- Consider MFA for administrators and restore approval.

---

## 18. Credential and Backup Security

Cisco configurations may contain sensitive information such as usernames, password hashes, SNMP communities, VPN settings, ACLs, and topology details.

Required safeguards:

- Use SSH for device access and HTTPS for the web application.
- Prefer a secrets manager for device credentials.
- If credentials are encrypted in the prototype, keep encryption keys outside source code and database backups.
- Encrypt backup storage at rest.
- Restrict backup download and restore permissions.
- Use least-privilege device accounts where supported.
- Validate SSH host keys where practical.
- Never place credentials in source code, logs, error messages, or Git.
- Add `.env`, private keys, credentials, logs, and generated backups to `.gitignore`.
- Keep audit logs protected against ordinary user modification.
- Restrict backup storage permissions and consider off-host copies.

A checksum detects accidental or unauthorized content changes only if the expected checksum is protected. For stronger integrity assurance, protect metadata and checksums with access controls or signed records.

---

## 19. Retention and Storage Management

Allow an administrator to configure:

- Maximum versions per device
- Maximum backup age
- Protected versions that cannot be automatically deleted
- Storage warning thresholds
- Storage location and capacity monitoring

Example policy:

```text
Keep last 30 distinct versions per device.
Keep protected versions until manually unprotected.
Warn at 80% storage usage.
Critical alert at 90% storage usage.
```

Retention must not delete the only recoverable configuration for a device. Run cleanup as a controlled background task, record deleted versions, and respect legal or organizational retention requirements.

---

## 20. Notifications and Reports

### Notify on

- Backup failure
- Device unreachable
- Repeated authentication failure
- Configuration change detected
- Restore success or failure
- Backup integrity failure
- Storage threshold exceeded
- Scheduler or worker failure

### Daily report fields

- Total devices targeted
- Successful, failed, and unchanged jobs
- Devices not reached
- Configuration changes detected
- Restore operations
- Storage usage
- Report generation time

Optional exports:

- CSV
- JSON
- PDF

Do not include credentials or full configuration text in emails or messaging alerts.

---

## 21. Optional Device-State Snapshots

These are useful for operational context but should remain separate from configuration backups.

Possible commands include:

```text
show version
show ip interface brief
show vlan brief
show ip route
```

Store each snapshot with a timestamp and clearly label it as operational state. Commands and output formats vary by platform and privilege level.

Keep the project focused on configuration management rather than expanding into a full network monitoring system.

---

## 22. Testing Plan

Use an isolated EVE-NG/GNS3 lab or authorized test equipment. Do not test restore workflows against production devices until the procedure has been validated and approved.

### Device tests

- Valid IP and SSH port
- Incorrect IP
- Device offline
- SSH disabled
- Invalid credentials
- Insufficient privilege
- Unsupported platform
- SSH host-key mismatch

### Backup tests

- Valid running configuration
- Valid startup configuration
- Empty or incomplete output
- CLI error returned as output
- Timeout during collection
- Connection dropped
- Unchanged configuration
- Changed configuration
- Checksum mismatch
- Storage unavailable
- Database unavailable

### Scheduler/job tests

- Due schedule creates jobs
- Disabled schedule creates no jobs
- Correct timezone handling
- Duplicate schedule execution prevention
- Concurrency limit enforced
- Retry limits respected
- Worker restart and queued jobs handled safely

### Diff tests

- No differences
- Added lines
- Removed lines
- Changed IP address
- Reordered or volatile lines
- Different device/platform versions
- Corrupted source version

### Restore tests

- Valid target version
- Invalid checksum
- Incompatible platform
- Pre-restore backup failure
- Permission denied
- Connection lost during restore
- Verification mismatch
- Recovery path
- Startup-save policy
- Audit log created for every outcome

### Security tests

- Unauthenticated API request
- Viewer attempts restore
- Operator attempts admin-only action
- Invalid session/token
- Login brute-force attempts
- Unauthorized backup download
- Credential leakage in logs
- Path traversal attempts
- Malicious input validation

---

## 23. Important Failure Cases

The system must fail safely and continue processing unrelated devices where possible.

| Failure | Required behavior |
|---|---|
| Device offline | Mark job failed or timed out; continue other jobs |
| SSH timeout | Apply bounded retry policy |
| Invalid credentials | Record failure; do not retry indefinitely |
| Incomplete configuration | Do not create a valid version |
| Configuration unchanged | Mark job successful and state unchanged |
| Corrupted backup | Block restore and alert |
| Database unavailable | Do not report success if metadata was not safely committed |
| Storage full | Stop unsafe writes and alert |
| Worker crash | Recover or mark stale jobs safely |
| Restore connection lost | Mark outcome uncertain and verify before any further action |
| Restore verification mismatch | Record failure/needs review and follow approved recovery procedure |
| Concurrent restore/backup | Serialize operations per device as configured |

---

## 24. Docker Deployment

Possible services:

```text
autonetops-frontend
autonetops-api
autonetops-postgres
autonetops-redis
autonetops-worker
autonetops-scheduler
```

Optional reverse proxy:

```text
nginx
```

Deployment considerations:

- Use persistent volumes for PostgreSQL and backup storage.
- Store secrets through deployment secrets or environment configuration.
- Do not publish the database or Redis ports publicly.
- Restrict network access from the application to approved device management networks.
- Use health checks and restart policies.
- Back up the AutoNetOps database and its configuration-storage metadata.
- Test restoration of the AutoNetOps platform itself.
- Use separate development, test, and production environments.

---

## 25. Development Roadmap

Build and test in small increments.

### Phase 1 — Project setup

- Create Git repository and folder structure.
- Set up Python virtual environment.
- Configure FastAPI.
- Configure PostgreSQL and migrations.
- Add `.env.example` and `.gitignore`.

**Deliverable:** Application starts and connects to the database.

### Phase 2 — Cisco lab connectivity

- Create an isolated EVE-NG/GNS3 lab.
- Configure management IP and SSH on a test device.
- Implement the Cisco driver.
- Test connection, authentication, and platform identification.

**Deliverable:** AutoNetOps can connect to an authorized lab device.

### Phase 3 — Device management

- Implement device create/read/update/delete.
- Add connection testing.
- Validate inputs and credential references.

**Deliverable:** Devices can be managed through the API.

### Phase 4 — Manual backup

- Collect running configuration.
- Collect startup configuration.
- Validate output.
- Store file and metadata.
- Record job results.

**Deliverable:** A user can create and view a backup.

### Phase 5 — Versioning and integrity

- Calculate SHA-256 checksums.
- Detect unchanged configurations.
- Create distinct versions.
- Verify backup integrity.

**Deliverable:** Configuration history is reliable.

### Phase 6 — Scheduled backup

- Add schedule CRUD operations.
- Add scheduler and background jobs.
- Implement concurrency limits, retries, and timeouts.

**Deliverable:** Backups run automatically on schedule.

### Phase 7 — Diff and change detection

- Compare versions.
- Display added and removed lines.
- Detect configuration changes.
- Add change timeline and notifications.

**Deliverable:** Administrators can identify changes between backups.

### Phase 8 — Controlled restore

- Validate selected version and permissions.
- Create pre-restore backup.
- Add explicit confirmation and optional approval.
- Implement platform-specific restore.
- Verify results and test recovery.

**Deliverable:** Restore works in the isolated lab with a tested recovery process.

### Phase 9 — Security and audit

- Add authentication and RBAC.
- Secure credentials and backup storage.
- Add audit logs and login protections.
- Test authorization on every sensitive endpoint.

**Deliverable:** Sensitive operations are controlled and traceable.

### Phase 10 — Frontend dashboard

- Build dashboard, device pages, backup history, diff viewer, schedules, job history, restore UI, reports, and settings.
- Add loading, empty, error, and confirmation states.

**Deliverable:** A complete web interface.

### Phase 11 — Reporting, retention, and deployment

- Add reports and exports.
- Implement retention policies.
- Add Docker deployment and health checks.
- Document installation, operations, and recovery.

**Deliverable:** A deployable, documented system.

### Phase 12 — Final validation

- Run the full test plan.
- Test database and storage failures.
- Test backup recovery.
- Test restore and recovery on every supported platform.
- Prepare screenshots, architecture diagrams, test evidence, and a demonstration.

**Deliverable:** A reproducible project demonstration and technical report.

---

## 26. Suggested MVP Scope

For the first working release, implement:

1. Cisco IOS/IOS-XE device registration
2. SSH connection testing
3. Manual running/startup configuration backup
4. Protected file storage and PostgreSQL metadata
5. Versioning and SHA-256 integrity checks
6. Scheduled backups
7. Configuration diff and change detection
8. Restore with pre-restore backup and explicit confirmation
9. Restore verification and tested recovery procedure
10. Basic authentication, roles, and audit logs
11. A functional dashboard and job history

Add multi-vendor support, selective restore, approval workflows, advanced change classification, and more integrations after the MVP is stable.

---

## 27. Definition of Done

The project is not complete just because a configuration file was downloaded. The MVP should meet these criteria:

- An authorized user can register a supported Cisco device.
- The system can test SSH connectivity and report failures clearly.
- Running and startup configurations can be collected and validated.
- Successful backups are stored with metadata and a checksum.
- Unchanged configurations do not create unnecessary duplicate versions.
- Scheduled backups execute at the configured local time.
- Failed jobs are logged and do not stop unrelated device jobs.
- Users can view history and compare two versions.
- Changes are recorded and can trigger notifications.
- Restore requires authorization, target validation, a pre-restore backup, and explicit confirmation.
- Restore results are verified and uncertain outcomes are clearly reported.
- Sensitive actions are auditable.
- Credentials and configuration files are protected.
- Tests demonstrate the expected behavior in an isolated lab.
- Installation, configuration, operation, limitations, and recovery are documented.

---

## 28. Final Project Description

> **AutoNetOps is a web-based network configuration management and automation platform that securely connects to Cisco network devices, performs scheduled and on-demand configuration backups, maintains versioned configuration history, detects configuration changes, provides visual configuration comparison, and enables controlled configuration restoration with pre-restore backups, verification, recovery support, audit logging, and role-based access control.**

The key difference between a simple backup script and AutoNetOps is the complete lifecycle: device management, scheduling, version history, change detection, safe restore, security, auditing, and operational reporting.

---

## 29. Important Implementation Notes

- Use only devices and networks you are authorized to administer.
- Validate restore operations on the exact target platform in an isolated lab before production use.
- Cisco restore behavior differs by operating system and release. There is no single universally safe restore command or rollback guarantee.
- A text diff does not prove that a configuration is semantically safe.
- A pre-restore backup helps recovery but cannot guarantee recovery if the device becomes unreachable.
- Do not claim real-time change detection unless a real-time event mechanism is implemented.
- Keep the raw configuration and document any normalization used for comparison.
- Never commit credentials, keys, production configurations, or generated backup files to a public repository.
