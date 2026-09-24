#!/usr/bin/env python3
"""
az-autobuild — the self-build loop. The piece that makes JARVIS build itself 24/7.

One bounded pass per wake (fired by sched-runner on the Mini). It does NOT loop
internally — runaway self-spawning is the scar we don't repeat. Each pass:

  1. Halt check (global kill-switch). Paused -> stand down.
  2. Pick the SINGLE next self-improvement item: an open architecture challenge,
     else an open self-build task, else the next cross-CLI foundation phase.
  3. GATE it by the unit's tier (read from the brain DB — this runs ON the Mini,
     the single-writer host, so it reads the DB directly like sched-runner does):
       contract/core/T2/T3 -> DO NOT execute. Propose to Shaan (ask + notify),
       log why, stop. capability/disposable/T0/T1 -> execute autonomously.
  4. Execute by waking a short, non-interactive agent-zero pass (claude -p) that
     loads the orchestrate skill and spawns workers INTO the headless `jarvis`
     herdr session — JARVIS's private sandbox, isolated from interactive tabs.
  5. Log the pass to the brain timeline.

Engine: AZ_ENGINE_MODEL routes the spawned pass through Bifrost. Once MiniMax
M3-highspeed is confirmed live in Bifrost, set AZ_ENGINE_MODEL to it. Until then
it falls back to claude's default (Opus) so the loop runs.

Run:  az-autobuild.py [--dry-run]
Env:
  SISO_DB           brain DB path (default ~/SISO_Workspace/.SystemDB/sisosystem.db)
  SISO_BRAIN_BIN    siso-brain client (for ask/notify/timeline writes)
  AZ_HERDR_SESSION  headless session to spawn into (default: jarvis)
  AZ_ENGINE_MODEL   model the spawned pass uses (default: claude's default)
  AZ_MAX_MINUTES    hard cap on the spawned pass (default 20)
"""
import argparse, json, os, sqlite3, subprocess, sys

HOME = os.path.expanduser("~")
BASE = f"{HOME}/SISO_Workspace/SISO_Agents/siso-agent-base"
DB = os.environ.get("SISO_DB", f"{HOME}/SISO_Workspace/.SystemDB/sisosystem.db")
SISO_BRAIN = os.environ.get("SISO_BRAIN_BIN", f"{BASE}/extensions/braind/siso-brain")
SESSION = os.environ.get("AZ_HERDR_SESSION", "jarvis")
# On the Mini, the 'haiku' tier routes through Bifrost -> MiniMax-M3-highspeed
# (routing_targets rule). So 'haiku' IS the M3 workhorse here. Default to it.
ENGINE_MODEL = os.environ.get("AZ_ENGINE_MODEL", "haiku")
MAX_MIN = int(os.environ.get("AZ_MAX_MINUTES", "20"))
ID = "agent-zero"

# tiers safe to execute autonomously vs tiers that must be proposed
AUTONOMOUS = {"t0", "t1", "disposable", "capability"}
GATED = {"t2", "t3", "core", "contract"}


def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def working_context(c):
    """The 3-week mental model — what Shaan is actually working on. The loop
    reads this so it understands INTENT, not just the next ticket. Most recent
    project_context memory wins."""
    try:
        row = c.execute(
            "SELECT content FROM memories WHERE type='project_context' "
            "ORDER BY created_at DESC LIMIT 1").fetchone()
        return row["content"] if row else ""
    except Exception:
        return ""


def brain(*args):
    """siso-brain client — used for the write side (ask/notify/timeline)."""
    try:
        subprocess.run([sys.executable, SISO_BRAIN, *args],
                       capture_output=True, text=True, timeout=25)
    except Exception:
        pass


def halted(c):
    row = c.execute(
        "SELECT 1 FROM control_flags WHERE scope='global' AND paused=1").fetchone()
    return row is not None


def pick_work(c):
    """(target_id, kind, prompt) for the next self-build item, or None."""
    # 1) open architecture challenges — the self-gaslight ledger.
    ch = c.execute(
        "SELECT id,target,argument FROM challenges WHERE verdict='open' "
        "ORDER BY created_at LIMIT 1").fetchone()
    if ch:
        return (ch["target"], "challenge",
                f"An open architecture challenge needs adjudication.\n"
                f"Target unit: {ch['target']}\n"
                f"Challenger argument: {ch['argument']}\n\n"
                f"Decide if the challenger beats the reigning champion. If it does "
                f"AND the change is capability-tier (revisable, in-lane), implement "
                f"it and resolve the challenge in the brain. If it touches the LOOP "
                f"(contract) or needs spend/destructive action, do NOT implement — "
                f"file the recommendation to Shaan and mark it logged-why-not.")

    # 2) open self-build tasks (tagged 'self-build' or assigned to the autobuild lane)
    t = c.execute(
        "SELECT id,title,description FROM tasks "
        "WHERE status IN ('pending','open','todo','in_progress') "
        "AND (tags LIKE '%self-build%' OR assigned_agent_id='agent-zero') "
        "AND archived_at IS NULL "
        "ORDER BY urgency_score DESC, created_at LIMIT 1").fetchone()
    if t:
        return (f"task/{t['id']}", "task",
                f"Self-build task: {t['title']}\n{t['description']}\n\n"
                f"Complete it if capability-tier and in-lane. Mark it done in the "
                f"brain when VERIFIED (observe the artifact, don't just read code).")

    # 3) the cross-CLI foundation standing track (phase 1 = wiring map is NEXT)
    return ("docs/CROSS-CLI-FOUNDATION", "phase",
            "Advance the Cross-CLI Foundation track "
            "(docs/jarvis/CROSS-CLI-FOUNDATION.html). Find the first phase marked "
            "NEXT/todo and do its CHEAP RECON + ONE concrete step only — do not boil "
            "the ocean. Use codex exec / Haiku workers for the mechanical sweep. "
            "Vault-first + OBSERVE the real artifact before any delete. Report the "
            "milestone to the brain and to oracle-zero's inbox. Doctor stays green.")


def tier_of(c, target):
    """Tier from the units table; unregistered -> capability (safe default)."""
    row = c.execute("SELECT tier FROM units WHERE id=?", (target,)).fetchone()
    return (row["tier"] if row else "capability").lower()


def spawned_prompt(kind, prompt, context=""):
    ctx_block = (f"WHAT WE ARE WORKING ON (your durable mental model — use this to "
                 f"judge what actually matters; don't work on things that don't serve "
                 f"these threads):\n{context}\n\n" if context else "")
    return (
        "You are agent-zero running an AUTONOMOUS self-build pass on the Mac Mini. "
        "You are JARVIS building itself. Work in the headless herdr session "
        f"'{SESSION}' — spawn workers there, never into Shaan's interactive tabs.\n\n"
        + ctx_block +
        "RULES (binding):\n"
        "- ONE bounded unit of progress this pass, then stop and report. No runaway loops.\n"
        "- Cheap compute: codex exec + Haiku workers for mechanical work. Reason briefly.\n"
        "- Vault-first: OBSERVE the real artifact (size+count+listing) before any delete.\n"
        "- Stay in-lane (capability tier). If the work needs cross-lane, spend, or "
        "destructive action, STOP and file it to Shaan via `siso-brain ask` + "
        "`siso-brain notify` instead of doing it.\n"
        "- Log what you did: siso-brain timeline --agent agent-zero --type ACTION --message ...\n\n"
        f"THIS PASS ({kind}):\n{prompt}\n")


def run_pass(kind, prompt, dry, context=""):
    instruction = spawned_prompt(kind, prompt, context)
    cmd = ["claude", "-p", instruction, "--dangerously-skip-permissions"]
    if ENGINE_MODEL:
        cmd[2:2] = ["--model", ENGINE_MODEL]
    env = dict(os.environ)
    env["HERDR_SESSION"] = SESSION
    env["HERDR_SOCKET_PATH"] = f"{HOME}/.config/herdr/sessions/{SESSION}/herdr.sock"
    if dry:
        print(f"[dry-run] claude -p (model={ENGINE_MODEL or 'default'}) session={SESSION}\n"
              f"--- instruction ---\n{instruction}")
        return 0, "dry-run"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=MAX_MIN * 60, env=env)
        return r.returncode, (r.stdout or r.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        return 124, f"pass exceeded {MAX_MIN}m cap (bounded-stop)"
    except Exception as e:
        return 1, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    c = db()
    if halted(c):
        print("global halt active — az-autobuild standing down")
        return

    ctx = working_context(c)
    picked = pick_work(c)
    if not picked:
        print("no self-build work queued — idle")
        return
    target, kind, prompt = picked
    tier = tier_of(c, target)
    print(f"picked {kind} target={target} tier={tier}")

    if tier in GATED:
        brain("ask", "--from-agent", ID, "--question",
              f"[autobuild] next self-build item is {tier}-tier ({target}). "
              f"Approve before I act:\n{prompt[:400]}")
        brain("notify", "--from-agent", ID, "--urgency", "normal",
              "--summary", f"autobuild paused on {tier}-tier item: {target}",
              "--body", prompt[:600])
        brain("timeline", "--agent", ID, "--type", "ACTION",
              "--message", f"autobuild proposed (gated {tier}) target={target}")
        print(f"gated ({tier}) — proposed to Shaan, not executed")
        return

    brain("timeline", "--agent", ID, "--type", "ACTION",
          "--message", f"autobuild pass START kind={kind} target={target} tier={tier}")
    code, tail = run_pass(kind, prompt, a.dry_run, ctx)
    status = "COMPLETED" if code == 0 else f"FAILED(rc={code})"
    brain("timeline", "--agent", ID,
          "--type", "COMPLETED" if code == 0 else "ACTION",
          "--message", f"autobuild pass {status} target={target} :: {tail[-300:]}")
    print(f"pass {status}")


if __name__ == "__main__":
    main()
