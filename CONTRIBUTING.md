# Contributing

Changes should strengthen one of three outcomes: a better identity contract, a more portable brain adapter, or a safer explicit handoff to an agent host.

Before opening a change:

1. State which outcome changes and why it belongs here.
2. Keep external systems behind environment or command contracts.
3. Add or update a deterministic smoke in `scripts/check_repo.py`.
4. Run `npm test` and include the result.

Machine-specific adapters are welcome when they are isolated, opt-in, and independently removable.
