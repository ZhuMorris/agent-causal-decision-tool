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
- **Local-only data**: Experiment history stored in `~/.agent-causal/history.db`

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7   | :x:                |

## Security Announcements

For any security-related announcements, follow the [GitHub Security Advisories](https://github.com/ZhuMorris/agent-causal-decision-tool/security/advisories) for this repository.