# Provenance

This repository is a clean extraction from the SISO-owned Agent Base warehouse, observed 2026-07-30.

Source boundary: `$SISO_WORKSPACE/SISO_Agent_Base/extensions/agent-zero/`.

The extraction refactors rather than blindly copies host state:

- `az-boot.py` and `agent-zero` became the provider-neutral `src/agent_zero.py`, the durable identity contract, and the thin executable.
- `open-siso-base.sh` became the environment-configured cmux adapter.
- personal workspace paths, a personal network endpoint, implicit credential-file reads, and implicit permission bypasses were removed.

Not promoted in this release:

- `az-voice.sh`: useful macOS voice adapter, but still couples microphone, Whisper, a specific agent host, and operating-system speech.
- `az-autobuild.py`: experimental self-build policy coupled to a live database schema, Herdr session, and provider route; it needs an explicit authority and dry-run contract.
- `new-agent.sh`: agent-home and organization scaffolding, not Agent Zero identity/boot behavior; it belongs with Project OS or a future agent-organization Work.

The warehouse remains untouched. This repository has its own release lifecycle from the extraction point onward.
