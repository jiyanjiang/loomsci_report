# LoomSci Report

Minimal Report app for LoomSci Core.

This version provides the app boundary and a persisted background job. It writes
the result back to Core as an item. The online research pipeline is the next
implementation step.

## Manifest

`slug=report`, `package=loomsci_report`, `entry=server`, health `/health`.

## Writing style

See [docs/perspective-style.md](docs/perspective-style.md) and [prompts/perspective.md](prompts/perspective.md).

## Iterative writing

See [docs/writing-loop.md](docs/writing-loop.md) and [prompts/critic.md](prompts/critic.md).
