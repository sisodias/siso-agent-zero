#!/usr/bin/env python3
"""
az-boot — agent-zero's rehydrate / boot sequence (kills amnesia).

agent-zero is the ONE agent Shaan talks to. It is not a new model — it is an
identity + brain-wiring around whatever CLI hosts it (Claude Code today). Its
defining property: it WAKES UP knowing the state of the whole ecosystem,
because the first thing it does is read the brain.

This script produces agent-zero's boot briefing by reading the brain-API:
  - the live fleet (who's running, where)
  - open tasks (what's in flight)
  - recent durable memories (what it knows)
  - recent timeline (what just happened)

Run at the start of an agent-zero session; pipe the output into the model's
context. It also writes a BOOT timeline event so the brain records the wake-up.

Usage:  az-boot.py [--id agent-zero] [--json]
Env:    SISO_BRAIN_URL / SISO_BRAIN_TOKEN (else auto-resolved like siso-brain)
"""
import argparse, json, os, subprocess, sys

HOME = os.path.expanduser("~")
SISO_BRAIN = os.environ.get("SISO_BRAIN_BIN",
                            f"{HOME}/SISO_Workspace/SISO_Agents/siso-agent-brain/extensions/braind/siso-brain")


def brain(*args):
    """Call the siso-brain client, return parsed JSON (or {} on failure)."""
    try:
        out = subprocess.run([sys.executable, SISO_BRAIN, *args],
                             capture_output=True, text=True, timeout=20)
        return json.loads(out.stdout) if out.stdout.strip() else {}
    except Exception as e:
        return {"error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="agent-zero")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    health = brain("health")
    fleet = brain("fleet")
    tasks = brain("tasks")
    mem = brain("memory-recall", "--q", "")  # most-relevant recent memories
    online = health.get("ok", False)
    halt = brain("halt-status")
    paused = halt.get("global_paused", False) if isinstance(halt, dict) else False

    # record the wake-up in the brain (best-effort; queues if offline)
    brain("timeline", "--agent", a.id, "--type", "BOOT",
          "--message", "agent-zero boot/rehydrate")
    brain("heartbeat", "--id", a.id, "--name", "agent-zero (the one you talk to)",
          "--status", "running")

    fleet_list = fleet.get("fleet", [])
    running = [f for f in fleet_list if f.get("status") == "running"]
    task_list = tasks.get("tasks", [])
    mems = mem.get("memories", [])

    if a.json:
        print(json.dumps({"brain_online": online, "fleet": fleet_list,
                          "running_count": len(running), "tasks": task_list,
                          "memories": mems}, indent=2))
        return

    # human/agent-readable briefing (this goes into the model context)
    questions = brain("questions").get("questions", [])
    L = []
    L.append("=== AGENT-ZERO BOOT BRIEFING ===")
    L.append(f"brain: {'ONLINE' if online else 'UNREACHABLE (degraded — reads from cache, writes queue)'}"
             + (f" | {health.get('timeline_events')} events on record" if online else ""))
    if paused:
        L.append("⛔ FLEET IS PAUSED (global halt active) — do NOT spawn or start work until resumed (`siso-brain halt --resume`).")
    if questions:
        L.append(f"❓ {len(questions)} question(s) awaiting Shaan's answer:")
        for qq in questions[:5]:
            L.append(f"   - {qq.get('question','')[:90]}")
    L.append("")
    L.append(f"FLEET — {len(running)} running / {len(fleet_list)} total:")
    for f in running[:12]:
        L.append(f"  • {f.get('name') or f.get('id')}  [{f.get('machine') or '?'}]  {f.get('cwd','')[:60]}")
    if not running:
        L.append("  (no agents currently running)")
    L.append("")
    L.append(f"OPEN TASKS — {len(task_list)}:")
    for t in task_list[:12]:
        L.append(f"  • [{t.get('status')}] {t.get('title') or t.get('description','')[:70]}")
    if not task_list:
        L.append("  (no open tasks)")
    L.append("")
    L.append(f"MEMORY — {len(mems)} recalled (highest confidence first):")
    for m in mems[:10]:
        L.append(f"  • ({m.get('tier')}, {m.get('confidence')}) {m.get('content','')[:90]}")
    if not mems:
        L.append("  (memory empty — nothing learned yet)")
    L.append("")
    # the org at a glance (tier-1 view: divisions + their latest status)
    roundup = brain("roundup").get("divisions", [])
    if roundup:
        L.append("DIVISIONS (your org — delegate to these, don't do their work yourself):")
        for x in roundup:
            z = x.get("zero_agent") or "(no zero yet)"
            st = (x.get("latest_status") or "idle")[:60]
            opn = x.get("open_intents", 0)
            L.append(f"  • {x.get('id')}  [{z}]  open={opn}  last: {st}")
        L.append("")
    L.append("You are SYSTEM-WIDE agent-zero — the ONE Shaan talks to. You span ALL divisions.")
    L.append("You do NOT run workers. You DELEGATE to project-zeros and read status back:")
    L.append("  • delegate:  siso-brain delegate --division <id> --intent \"<what>\"")
    L.append("  • check org: siso-brain roundup")
    L.append("  • a division reports up via: siso-brain inbox-reply (project-zeros do this, not you)")
    L.append("Each division has its own <project>-zero (plan-holder) + orchestrator (runs the orchestrate skill to drive herdr workers).")
    L.append("Record decisions: siso-brain memory-write. Progress: siso-brain timeline. Ask Shaan: siso-brain ask.")
    L.append("Autonomy: T0 read / T1 write-in-lane = ungated; T2 cross-lane/spawn = propose+approve; T3 spend/destructive = always gated.")
    print("\n".join(L))


if __name__ == "__main__":
    main()
