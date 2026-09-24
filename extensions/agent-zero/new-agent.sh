#!/bin/zsh
# new-agent — stamp the canonical SISO agent-folder skeleton (the oracle-streaming convention),
# system-wide. Creates identity.yaml + CLAUDE.md + SOUL.md + memory/{brain,journal}.md +
# changelog.md + timeline.ndjson + inbox/ + outbox/, and registers the agent in the brain.
#
# This is how the org chart grows: agent-zero (or you) stamps a new agent home when a
# real recurring lane earns it. Agents need NOT be running to exist — they're documented
# folders + a brain row; spin them up on demand to save compute.
#
# Usage:
#   new-agent <division> <name> <role-tier> "<role description>" ["reports_to"]
#     role-tier: zero | orchestrator | worker
#   e.g. new-agent isso-dashboard isso-zero zero "ISSO division plan-holder; talks to agent-zero" agent-zero
#        new-agent isso-dashboard isso-orchestrator orchestrator "Owns ISSO herdr fleet" isso-zero
set -e
DIV="$1"; NAME="$2"; TIER="${3:-worker}"; ROLE="${4:-worker}"; REPORTS="${5:-orchestrator}"
[[ -z "$DIV" || -z "$NAME" ]] && { echo "usage: new-agent <division> <name> <zero|orchestrator|worker> \"<role>\" [reports_to]"; exit 1; }

WS="$HOME/SISO_Workspace"
# division -> repo path (where the agent folder lives). Falls back to a central home.
case "$DIV" in
  oracle-streaming) BASE="$WS/SISO_Agency/apps/oracle-streaming/agents" ;;
  isso-dashboard)   BASE="$WS/SISO_Agency/apps/isso-dashboard/agents" ;;
  agency)           BASE="$WS/SISO_Agency/agents" ;;
  internal-lab)     BASE="$WS/SISO_Internal_Lab/agents" ;;
  library)          BASE="$WS/SISO_Knowledge/agents" ;;
  team-entrepreneurship) BASE="$WS/personal/team-entrepreneurship/agents" ;;
  agent-base|system) BASE="$WS/SISO_Agents/siso-agent-base/.siso/agents" ;;
  *) BASE="$WS/SISO_Agents/siso-agent-base/.siso/agents/$DIV" ;;   # central home for new divisions
esac

DIR="$BASE/$NAME"
if [[ -d "$DIR" ]]; then echo "agent home already exists: $DIR"; exit 0; fi
mkdir -p "$DIR/memory" "$DIR/inbox" "$DIR/outbox"
touch "$DIR/inbox/.gitkeep" "$DIR/outbox/.gitkeep"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DATE="$(date -u +%Y-%m-%d)"

cat > "$DIR/identity.yaml" <<YAML
name: $NAME
role: "$ROLE"
tier: $TIER          # zero | orchestrator | worker
engine: claude
model: opus
division: $DIV
reports_to: $REPORTS
uses_skill: orchestrate   # ~/.claude/skills/orchestrate (orchestrators/zeros)
home: $DIR
scope: lightweight-local
brain: via siso-brain (timeline/memory/delegate/roundup/inbox)
created: $DATE
YAML

cat > "$DIR/CLAUDE.md" <<MD
# $NAME — charter

**Tier:** $TIER · **Division:** $DIV · **Reports to:** $REPORTS

$ROLE

## Boot sequence (every session, in order)
1. Read this CLAUDE.md → identity.yaml → SOUL.md
2. Read memory/brain.md (durable lessons + current state), then memory/journal.md (run log)
3. \`ls -t inbox/\` — newest first; process anything open
4. If orchestrator/zero: load the \`orchestrate\` skill (~/.claude/skills/orchestrate)
5. Sync with the brain: \`siso-brain roundup\` (zeros) / \`siso-brain inbox --division $DIV\` (zeros) / \`siso-brain fleet\`
6. Heartbeat: \`siso-brain heartbeat --id $NAME --machine \$(hostname) --status running\`

## How I persist (no amnesia)
- Durable learning → append to memory/brain.md
- Running decisions/log → append to memory/journal.md
- Material events → \`siso-brain timeline --agent $NAME --type <BOOT|ACTION|HANDOFF|COMPLETED> --message "..."\`
- Async to another agent → drop a timestamped file in their inbox/ (and via brain for cross-machine)

## Channels
- Live: \`herdr pane run <id> "..."\` while both awake
- Durable: inbox/ + outbox/ (timestamped, signed \`[from: $NAME]\`) + the brain (cross-machine)

## Autonomy tiers (binding)
T0 read = ungated · T1 write-in-lane = ungated · T2 cross-lane/spawn = propose→approve · T3 spend/destructive/external = always gated.
MD

cat > "$DIR/SOUL.md" <<MD
# $NAME — soul

Voice & values. (Stamped $DATE — refine as the agent earns its character.)

- Terse, first-principles, decide-and-announce. Absorb noise from the tier below; report compact signal to the tier above.
- $( [[ "$TIER" == zero ]] && echo "Hold the plan + memory for $DIV. Talk to agent-zero (up) and the orchestrator (down). Never drown in worker noise." )
- $( [[ "$TIER" == orchestrator ]] && echo "Own the herdr worker fleet. The 5 Laws are binding. Gate completion on handoff PASS, never on agent_status." )
- $( [[ "$TIER" == worker ]] && echo "Do ONE job well. Write a PASS/FAIL handoff before claiming done. Stop and report when blocked." )
MD

cat > "$DIR/memory/brain.md" <<MD
# $NAME — Brain (durable memory)

Durable lessons + current state for $NAME ($DIV). My learning, not transcripts.

---

## Charter (decided $DATE)
$ROLE
Tier $TIER, reports to $REPORTS.

## Lessons
(none yet — append as scars/wins accumulate)

## Current state
Stamped $DATE. Awaiting first intent.
MD

cat > "$DIR/memory/journal.md" <<MD
# $NAME — Journal (run log)

## $NOW — created
Agent home stamped from the canonical skeleton. Registered in the brain.
MD

cat > "$DIR/changelog.md" <<MD
# $NAME — Changelog

- $DATE: created (tier=$TIER, division=$DIV, reports_to=$REPORTS).
MD

echo "{\"ts\":\"$NOW\",\"event\":\"created\",\"tier\":\"$TIER\",\"division\":\"$DIV\"}" > "$DIR/timeline.ndjson"

# register in the brain (best-effort)
[[ -z "$SISO_BRAIN_TOKEN" && -f "$HOME/.siso/brain-tokens/write.token" ]] && export SISO_BRAIN_TOKEN="$(cat "$HOME/.siso/brain-tokens/write.token")"
siso-brain heartbeat --id "$NAME" --name "$NAME ($DIV $TIER)" --machine "$(hostname -s)" --status idle >/dev/null 2>&1 || true
if [[ "$TIER" == "zero" ]]; then
  # mark this as the division's zero
  siso-brain division-register --id "$DIV" --name "$DIV" --status active >/dev/null 2>&1 || true
fi
siso-brain timeline --agent "$NAME" --type BOOT --message "agent home created (tier=$TIER, division=$DIV)" >/dev/null 2>&1 || true

echo "✅ stamped agent home: $DIR"
echo "   launch:  cd $DIR && claude --dangerously-skip-permissions"
echo "   files:   identity.yaml · CLAUDE.md · SOUL.md · memory/{brain,journal}.md · changelog.md · timeline.ndjson · inbox/ · outbox/"
