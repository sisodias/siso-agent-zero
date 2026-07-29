#!/usr/bin/env python3
"""Deterministic publication and behavior checks for SISO Agent Zero."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md", "LICENSE", "AGENTS.md", "PROVENANCE.md", "MIGRATION-MAP.json",
    "install.sh", "uninstall.sh",
    "config/identity.md", "bin/siso-agent-zero", "src/agent_zero.py",
    "adapters/cmux/open-siso-base.sh", "docs/ARCHITECTURE.html",
]
TEXT_SUFFIXES = {".md", ".html", ".json", ".jsonl", ".py", ".sh", ""}
FORBIDDEN = [
    "/" + "Users/",
    "dangerously-" + "skip-permissions",
    "sk-" + "or-v1-",
    "gh" + "p_",
    "github" + "_pat_",
]


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True, **kwargs)


def check_files() -> None:
    for relative in REQUIRED:
        assert (ROOT / relative).is_file(), f"missing required file: {relative}"
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        assert not path.is_symlink(), f"symlink is not publishable: {path.relative_to(ROOT)}"
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for value in FORBIDDEN:
                assert value not in text, f"forbidden publication pattern {value!r} in {path.relative_to(ROOT)}"


def check_syntax() -> None:
    for path in ROOT.rglob("*.py"):
        if ".git" not in path.parts:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
    run(["zsh", "-n", "bin/siso-agent-zero"])
    run(["zsh", "-n", "install.sh"])
    run(["zsh", "-n", "uninstall.sh"])
    run(["zsh", "-n", "adapters/cmux/open-siso-base.sh"])
    json.loads((ROOT / "MIGRATION-MAP.json").read_text(encoding="utf-8"))


def write_fake_brain(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys
log = pathlib.Path(__file__).with_suffix('.log')
command = sys.argv[1] if len(sys.argv) > 1 else ''
if command in {'timeline', 'heartbeat'}:
    log.write_text(log.read_text() + command + '\\n' if log.exists() else command + '\\n')
responses = {
  'health': {'ok': True},
  'fleet': {'fleet': [{'id': 'worker-1', 'status': 'running'}]},
  'tasks': {'tasks': [{'id': 'task-1', 'title': 'Verify the extraction'}]},
  'memory-recall': {'memories': [{'content': 'Keep repository boundaries outcome-based.'}]},
  'questions': {'questions': []},
  'halt-status': {'global_paused': False},
  'roundup': {'divisions': [{'id': 'library', 'name': 'Great Library'}]},
}
print(json.dumps(responses.get(command, {'ok': True})))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def check_behavior() -> None:
    with tempfile.TemporaryDirectory(prefix="siso-agent-zero-check-") as folder:
        fake = Path(folder) / "fake-brain"
        write_fake_brain(fake)
        env = os.environ.copy()
        env["SISO_BRAIN_BIN"] = str(fake)

        brief = run(["bin/siso-agent-zero", "--brief"], env=env).stdout
        assert "brain: ONLINE" in brief
        assert "Verify the extraction" in brief
        assert not fake.with_suffix(".log").exists(), "read-only boot unexpectedly announced"

        payload = json.loads(run(["bin/siso-agent-zero", "--json"], env=env).stdout)
        assert payload["brain_online"] is True
        assert payload["agent_id"] == "agent-zero"

        packet = run(["bin/siso-agent-zero", "--task", "Hold this intent"], env=env).stdout
        assert "You are Agent Zero" in packet and "Hold this intent" in packet

        forwarded = run([
            "bin/siso-agent-zero", "--task", "Forward safely", "--exec",
            sys.executable, "-c", "import sys; data=sys.stdin.read(); print('FORWARDED' if 'Forward safely' in data else 'MISSING')",
        ], env=env).stdout
        assert forwarded.strip() == "FORWARDED"

        run(["bin/siso-agent-zero", "--announce", "--brief"], env=env)
        writes = fake.with_suffix(".log").read_text(encoding="utf-8").splitlines()
        assert writes == ["timeline", "heartbeat"]

        install_root = Path(folder) / "installed"
        bin_root = Path(folder) / "bin"
        install_env = env.copy()
        install_env["SISO_AGENT_ZERO_HOME"] = str(install_root)
        install_env["SISO_BIN_DIR"] = str(bin_root)
        run(["zsh", "install.sh"], env=install_env)
        installed = bin_root / "siso-agent-zero"
        assert installed.is_symlink()
        installed_brief = subprocess.run(
            [str(installed), "--brief"], cwd=ROOT, env=install_env,
            text=True, capture_output=True, check=True,
        ).stdout
        assert "brain: ONLINE" in installed_brief
        run(["zsh", "uninstall.sh"], env=install_env)
        assert not install_root.exists() and not installed.exists()


def main() -> None:
    check_files()
    check_syntax()
    check_behavior()
    print("AGENT_ZERO_CHECK_OK (publication, syntax, read-only boot, explicit announce, explicit host handoff)")


if __name__ == "__main__":
    main()
