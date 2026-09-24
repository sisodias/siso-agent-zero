#!/bin/zsh
# az-voice — TALK to JARVIS. Voice in → Opus agent-zero (brain-aware) → voice out.
#
# Loop:  you press Enter → records mic until you press Enter again →
#        whisper transcribes → agent-zero (Opus, booted from the brain) answers →
#        macOS `say` speaks the reply. Repeat. Ctrl-C to quit.
#
# Everything local + free: sox (mic) · whisper (STT) · claude/Opus (brain) · say (TTS).
# Each turn boots agent-zero with the live brain briefing so it knows the whole org.
#
# Usage:  az-voice            (interactive voice loop)
#         az-voice --once "text"   (skip mic, type once — for testing)
set -e
# auto-load the local write token so nested siso-brain calls authenticate
[[ -z "$SISO_BRAIN_TOKEN" && -f "$HOME/.siso/brain-tokens/write.token" ]] && export SISO_BRAIN_TOKEN="$(cat "$HOME/.siso/brain-tokens/write.token")"
AZ_DIR="${0:A:h}"
BOOT="$AZ_DIR/az-boot.py"
TMP="/tmp/az-voice"; mkdir -p "$TMP"
VOICE="${AZ_VOICE:-Daniel}"          # macOS voice; `say -v ?` to list
WHISPER_MODEL="${AZ_WHISPER_MODEL:-base.en}"

SAY_RATE="${AZ_SAY_RATE:-160}"       # words/min — lower = slower/calmer
say_it(){ say -v "$VOICE" -r "$SAY_RATE" "$1" 2>/dev/null & }

# Build the system context once per turn (fresh brain state = no amnesia).
brief(){ python3 "$BOOT" --id agent-zero 2>/dev/null; }

ask_agent_zero(){
  local utterance="$1"
  local prompt="You are SYSTEM-WIDE agent-zero — Shaan's chief of staff, spoken aloud. Give ONLY the HIGHEST-LEVEL answer: the single headline Shaan needs, the way a CEO wants a one-breath briefing from their right hand.

HARD RULES for your reply:
- 1 sentence by default. 2 only if truly necessary. NEVER more.
- Only the top-level signal. NO lists, NO numbers-dumps, NO per-division breakdowns, NO task IDs, NO jargon, NO markdown, NO code.
- If everything's quiet, say so in a few words. If ONE thing needs him, lead with that.
- If he asks you to DO something, do it via siso-brain and confirm in one short sentence.
- Talk like a calm human colleague, not a report. He can ask 'tell me more' to drill in.

$(brief)

Shaan said (voice): \"$utterance\"

Your reply — ONE high-level spoken sentence (two max):"
  echo "$prompt" | claude -p --dangerously-skip-permissions 2>/dev/null
}

if [[ "$1" == "--once" ]]; then
  resp="$(ask_agent_zero "$2")"
  print -r -- "agent-zero: $resp"
  say_it "$resp"; wait
  exit 0
fi

echo "🎙️  az-voice — talk to JARVIS (agent-zero / Opus). Ctrl-C to quit."
say_it "Agent zero online. I can see all your divisions. What do you need?"
while true; do
  print -n "\n[Enter to talk, then Enter again to stop recording] "; read _
  echo "🔴 recording… (Enter to stop)"
  # record in background, stop on next Enter
  sox -d -q "$TMP/in.wav" 2>/dev/null &
  REC=$!
  read _
  kill "$REC" 2>/dev/null; sleep 0.2
  echo "📝 transcribing…"
  whisper "$TMP/in.wav" --model "$WHISPER_MODEL" --language en --output_dir "$TMP" --output_format txt >/dev/null 2>&1 || true
  utterance="$(cat "$TMP/in.txt" 2>/dev/null | tr '\n' ' ' | sed 's/^ *//;s/ *$//')"
  if [[ -z "$utterance" ]]; then echo "(heard nothing — try again)"; continue; fi
  echo "🗣️  you: $utterance"
  echo "🤖 agent-zero thinking…"
  resp="$(ask_agent_zero "$utterance")"
  print -r -- "🔊 agent-zero: $resp"
  # log the exchange to the brain timeline
  siso-brain timeline --agent agent-zero --type USER_PROMPT --message "voice: $utterance" >/dev/null 2>&1 || true
  say_it "$resp"; wait
done
