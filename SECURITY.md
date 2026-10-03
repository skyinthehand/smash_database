# Security Policy

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues, pull requests, or discussions.

Instead, report them privately via GitHub's
[Private vulnerability reporting](https://github.com/skyinthehand/smash_database/security/advisories/new)
(**Security** tab → **Report a vulnerability**).

Please include:

- A description of the issue and its potential impact
- Steps to reproduce, or a proof of concept
- Affected files, workflows, or commits, if known

You can expect an initial response within 7 days. Once the issue is confirmed, a fix will be prepared and a GitHub Security Advisory will be published as appropriate.

## Scope

This repository contains data collection scripts, GitHub Actions workflows, and tournament data collected from [start.gg](https://www.start.gg/).

In scope:

- Vulnerabilities in the scripts or GitHub Actions workflows in this repository
- Accidentally exposed credentials (e.g. API tokens) in the repository or its history

Out of scope:

- Vulnerabilities in start.gg itself — please report those to start.gg directly
- Inaccuracies in the collected tournament data — please open a regular issue instead
