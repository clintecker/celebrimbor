# Security Policy

## Supported versions

Celebrimbor is pre-1.0. Security fixes are applied to the latest released
version.

| Version | Supported |
|---|---|
| 0.1.x | ✅ |

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than opening a public
issue. Use GitHub's [private vulnerability
reporting](https://github.com/clintecker/celebrimbor/security/advisories/new) on
this repository.

Include, where you can:

- a description of the issue and its impact,
- the smallest reproduction you can produce,
- the version and environment.

We aim to acknowledge reports within a few days and to keep you informed as we
work on a fix.

## Scope

Celebrimbor runs commodity tools as subprocesses with fixed argument vectors and
no shell, and reads project data files (YAML/TOML) it does not execute. The most
relevant surfaces are therefore the subprocess invocation layer
(`celebrimbor.commodity`) and the ledger/config parsers. Reports touching those
are especially welcome.
