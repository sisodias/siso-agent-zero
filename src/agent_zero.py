#!/usr/bin/env python3
"""Build and optionally hand off a portable Agent Zero boot packet."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PATH = ROOT / "config" / "identity.md"


def brain_command() -> list[str]:
    encoded = os.environ.get("SISO_BRAIN_COMMAND_JSON")
    if encoded:
        value = json.loads(encoded)
        if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
            raise ValueError("SISO_BRAIN_COMMAND_JSON must be a non-empty JSON string array")
        return value
    return [os.environ.get("SISO_BRAIN_BIN", "siso-brain")]


def call_brain(arguments: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [*brain_command(), *arguments],
            capture_output=True,
            text=True,
            timeout=float(os.environ.get("SISO_BRAIN_TIMEOUT_SECONDS", "10")),
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"error": f"brain command failed ({result.returncode})"}
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else {"error": "brain response was not an object"}
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError) as error:
        return {"error": str(error)}


def collect_state(agent_id: str, announce: bool) -> dict[str, Any]:
    state = {
        "health": call_brain(["health"]),
        "fleet": call_brain(["fleet"]),
        "tasks": call_brain(["tasks"]),
        "memories": call_brain(["memory-recall", "--q", ""]),
        "questions": call_brain(["questions"]),
        "halt": call_brain(["halt-status"]),
        "roundup": call_brain(["roundup"]),
    }
    state["brain_online"] = bool(state["health"].get("ok"))
    state["agent_id"] = agent_id
    if announce:
        call_brain(["timeline", "--agent", agent_id, "--type", "BOOT", "--message", "agent-zero boot/rehydrate"])
        call_brain(["heartbeat", "--id", agent_id, "--name", "Agent Zero", "--status", "running"])
    return state


def object_list(container: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = container.get(key, [])
    return value if isinstance(value, list) else []


def render_brief(state: dict[str, Any]) -> str:
    fleet = object_list(state["fleet"], "fleet")
    running = [item for item in fleet if item.get("status") == "running"]
    tasks = object_list(state["tasks"], "tasks")
    memories = object_list(state["memories"], "memories")
    questions = object_list(state["questions"], "questions")
    divisions = object_list(state["roundup"], "divisions")
    paused = bool(state["halt"].get("global_paused"))

    lines = ["=== AGENT ZERO BOOT BRIEFING ==="]
    lines.append("brain: ONLINE" if state["brain_online"] else "brain: UNREACHABLE — coordination state is degraded")
    if paused:
        lines.append("fleet: PAUSED — do not start new work")
    if questions:
        lines.append(f"questions awaiting a human: {len(questions)}")

    lines.extend(["", f"FLEET — {len(running)} running / {len(fleet)} known"])
    for item in running[:12]:
        lines.append(f"- {item.get('name') or item.get('id') or 'unnamed agent'}")

    lines.extend(["", f"OPEN TASKS — {len(tasks)}"])
    for item in tasks[:12]:
        lines.append(f"- {item.get('title') or item.get('description') or item.get('id') or 'untitled task'}")

    lines.extend(["", f"MEMORY — {len(memories)} recalled"])
    for item in memories[:10]:
        lines.append(f"- {item.get('content') or ''}".rstrip())

    lines.extend(["", f"DIVISIONS — {len(divisions)}"])
    for item in divisions[:12]:
        lines.append(f"- {item.get('name') or item.get('id') or 'unnamed division'}")
    return "\n".join(lines)


def boot_packet(state: dict[str, Any], task: str | None) -> str:
    identity = IDENTITY_PATH.read_text(encoding="utf-8").strip()
    pieces = [identity, "--- CURRENT SHARED STATE ---", render_brief(state), "--- END SHARED STATE ---"]
    if task:
        pieces.extend(["CURRENT TASK", task.strip()])
    return "\n\n".join(pieces) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", default="agent-zero", help="Agent identity used for optional announcements")
    parser.add_argument("--task", help="Current human intent to append to the boot packet")
    parser.add_argument("--brief", action="store_true", help="Print only the human-readable shared-state briefing")
    parser.add_argument("--json", action="store_true", help="Print the collected shared state as JSON")
    parser.add_argument("--announce", action="store_true", help="Explicitly record a BOOT event and heartbeat")
    parser.add_argument("--exec", dest="exec_command", nargs=argparse.REMAINDER, help="Explicit command that receives the boot packet on stdin")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = collect_state(args.id, args.announce)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    if args.brief:
        print(render_brief(state))
        return 0

    packet = boot_packet(state, args.task)
    command = args.exec_command or []
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print(packet, end="")
        return 0
    try:
        completed = subprocess.run(command, input=packet, text=True, check=False)
        return completed.returncode
    except FileNotFoundError:
        print(f"Agent host not found: {shlex.join(command)}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
