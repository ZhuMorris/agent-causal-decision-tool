# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in this project, please report it via GitHub Security Advisories:

**DO NOT** report security issues by opening a public GitHub Issue.

## Scope

This tool processes statistical experiment data and maintains a local SQLite database. Security considerations include:

- **Input validation**: All CLI inputs are validated before processing
- **SQL injection**: Parameterized queries used exclusively (no string interpolation of user data)
- **Dependency vulnerabilities**: Keep dependencies updated; run `pip-audit` periodically
- **No network exposure**: The tool does not make outbound network requests
- **Local-only data**: Experiment history stored in `~/.agent-causal/history.db` (user-owned, not shared)

## Threat Model & Risk Justification

This tool is flagged by automated scanners for three behaviors: `exec` tool usage, remote git install, and local SQLite management. Here is why these are safe for this use case:

### exec tool usage
The skill uses `exec` exclusively to invoke its own CLI commands (e.g., `python3 -m src.cli ab`). It does **not** execute arbitrary shell commands, pipe user input into shell evaluation, or chain commands from untrusted sources. Commands are hardcoded, minimal, and scoped to the tool's own Python package.

### Remote git install (`pip install git+https://github.com/...`)
This pattern is flagged because pip fetches and executes code from the internet. Mitigation: the repository is a **single-author, personal repo** with no third-party dependencies beyond PyPI. The install URL is pinned to a specific git ref, not a branch. You can also clone once and install from local path:
```bash
git clone https://github.com/ZhuMorris/agent-causal-decision-tool.git ~/clawd/agent-causal-decision-tool
pip install ~/clawd/agent-causal-decision-tool  # local install, no git fetch
```

### Local SQLite database (~/.agent-causal/history.db)
SQLite is a local file database. It is **not a network service** and cannot be accessed remotely. The DB contains only experiment JSON blobs written by the tool itself. It is stored in the user's home directory with standard file permissions.

### Supply chain risk
The tool depends only on PyPI packages (`click`, `scipy`, `numpy`, `pydantic`). All are well-maintained, widely-used libraries with strong security track records. No internal/external scripts are fetched at install time.

## Supported Versions

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7   | :x:                |

## Security Announcements

For any security-related announcements, follow the [GitHub Security Advisories](https://github.com/ZhuMorris/agent-causal-decision-tool/security/advisories) for this repository.