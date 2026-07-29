# SISO Agent Zero

Agent Zero is the intent-holding coordination layer in the SISO Agent Stack. It creates a current boot packet from an Agent Brain, joins that state to a durable identity, and hands the result to an explicitly selected agent host.

It is **not** an agent framework, model runtime, task database, or Herdr control plane. Those are dependencies or neighboring Works with independent lifecycles.

## Try it

```bash
./install.sh
siso-agent-zero --brief

# Or run directly from a clone:
bin/siso-agent-zero --brief
bin/siso-agent-zero --json
bin/siso-agent-zero --task "Map the next repository boundary"
bin/siso-agent-zero --task "Review the stack" --exec claude -p
```

The safe default prints a boot packet. `--exec` is explicit, uses no shell, and sends the packet to the selected command over standard input.

The installer defaults to `~/.local/share/siso-agent-zero` and `~/.local/bin`. Override those with `SISO_AGENT_ZERO_HOME` and `SISO_BIN_DIR`; `./uninstall.sh` removes only an installation carrying this package's marker.

Configure a compatible brain CLI with `SISO_BRAIN_BIN` or a JSON command array in `SISO_BRAIN_COMMAND_JSON`. Use `--announce` only when Agent Zero should record its boot and heartbeat.

## Repository boundary

This first release contains:

- a provider-neutral boot packet and identity contract;
- a command-based Agent Brain adapter;
- an explicit host-command handoff;
- an optional, environment-configured cmux adapter.

It deliberately excludes the machine-specific voice loop, self-build loop, and agent-home scaffolder found in the source warehouse. Their dispositions and promotion gates are recorded in [`MIGRATION-MAP.json`](MIGRATION-MAP.json).

Read the human architecture at [`docs/ARCHITECTURE.html`](docs/ARCHITECTURE.html). Run `npm test` before publishing.

MIT licensed. The Great Library records immutable releases separately from this moving source branch.
