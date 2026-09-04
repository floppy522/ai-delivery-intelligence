# Security Policy

## Supported Versions

Only the current public `v0.1` release line is supported.

## Reporting a Vulnerability

Please do not open a public GitHub Issue for a potential vulnerability before
coordinated disclosure. Report it privately to
[malovvu03@gmail.com](mailto:malovvu03@gmail.com).

Include, where applicable:

- the affected component and version;
- reproduction steps;
- expected and actual behaviour;
- potential impact;
- a proof of concept, if it can be shared safely.

## Security Design

The [threat model](docs/threat-model.md) documents tracker credential handling,
trusted and untrusted boundaries, prompt injection, AI output validation, and
read-only agent permissions.
