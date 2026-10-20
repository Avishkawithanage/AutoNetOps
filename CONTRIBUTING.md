# Contributing

1. Fork, then create a branch from `main`.
2. Set up as described in [docs/RUNNING.md](docs/RUNNING.md).
3. Run the tests before opening a pull request: `backend\.venv\Scripts\python -m pytest` and `npm run build` in `frontend/`.
4. Keep changes focused and add tests for new behaviour.
5. Never include real device IPs, credentials, configurations or backup files in commits, issues or logs.

Restore logic touches live network devices: changes there need a test and a note on how they were validated.
