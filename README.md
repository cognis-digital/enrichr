# ENRICHR — Enrich a leads CSV with firmographics, tech stack, and contact validation from pluggable providers, caching results to avoid duplicate API spend.

> Part of the **[Cognis Neural Suite](https://github.com/cognis-digital)** by [Cognis Digital](https://cognis.digital)
> Cognis Open Collaboration License (COCL) v1.0 · domain: `bizdev`

[![PyPI](https://img.shields.io/pypi/v/cognis-enrichr.svg)](https://pypi.org/project/cognis-enrichr/)
[![CI](https://github.com/cognis-digital/enrichr/actions/workflows/ci.yml/badge.svg)](https://github.com/cognis-digital/enrichr/actions)
[![License: COCL 1.0](https://img.shields.io/badge/License-COCL%201.0-2b6cb0.svg)](LICENSE)
[![Suite](https://img.shields.io/badge/Cognis-Neural%20Suite-6b46c1.svg)](https://github.com/cognis-digital)

**Enrich a leads CSV with firmographics, tech stack, and contact validation from pluggable providers, caching results to avoid duplicate API spend..**

*Business Development — sales, outreach, CRM, and revenue ops.*

## Why

ENRICHR exists for one job — enrich a leads csv with firmographics, tech stack, and contact validation from pluggable providers, caching results to avoid duplicate api spend. — and does it without a SaaS bill or heavyweight setup.
Single-purpose, scriptable, CI-friendly, self-hostable, and callable by AI agents over MCP.

## Install

```bash
pip install cognis-enrichr
# or from this repo:
pip install -e ".[dev]"
```

## Quick start

```bash
enrichr --version
enrichr scan .                      # scan the current project
enrichr scan . --format json
enrichr scan . --fail-on high       # non-zero exit for CI gates
enrichr mcp                         # expose as an MCP server (Cognis.Studio / Claude Desktop / Cursor)
```

## Built-in demo scenarios

- [`demos/01-basic/`](demos/01-basic/SCENARIO.md)
- [`demos/02-clean/`](demos/02-clean/SCENARIO.md)
- [`demos/03-mixed/`](demos/03-mixed/SCENARIO.md)

## Inspiration / prior art

Built in the spirit of **Clearbit/Apollo enrichment, with a Singer-style pluggable provider interface**, re-framed for the Cognis approach: single-purpose, self-hostable,
MCP-native, and unified with the rest of the Suite. Missing a credit? Open a PR.

## How it fits the Cognis Neural Suite

`enrichr` is one of the **100+ tools** in the [Cognis Neural Suite](https://github.com/cognis-digital).
Every tool ships an MCP server, so [Cognis.Studio](https://cognis.studio) agents can call them as scoped capabilities.

- Design notes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Roadmap: [`ROADMAP.md`](ROADMAP.md)

## Contributing

PRs, new rules, and demo scenarios welcome under the collaboration-pull model — see
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License

Source-available under the **Cognis Open Collaboration License (COCL) v1.0** — free for personal,
internal-evaluation, research, and educational use; **commercial / production use requires a license**
(licensing@cognis.digital). See [LICENSE](LICENSE).

## About

**[Cognis Digital](https://cognis.digital)** — Wyoming, USA · *Making Tomorrow Better Today.*
