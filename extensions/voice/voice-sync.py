#!/usr/bin/env python3
"""
voice-sync — drains the SISO Voice outbox into the JARVIS spine.

The freeflow app (SpineOutbox.swift) appends ONE NDJSON line per dictation to
~/.siso/voice-outbox.ndjson (TEXT ONLY, never audio). This drainer POSTs each
line to braind's /voice/utterance using the same URL/token resolution as
siso-brain, then drops the lines it landed. Lines that fail transiently (brain
unreachable or 5xx) are rewritten back atomically and retried next run. Lines
the brain PERMANENTLY rejects (4xx) and malformed lines are preserved verbatim
in ~/.siso/voice-outbox.deadletter.ndjson and never re-POSTed — re-queueing
them forever is what produced the 2026-08-13 400-retry storm (TASK-0010 V2).

braind does ON CONFLICT(client_id) upsert, so re-POSTing the same utterance is
idempotent — safe to run on a tight launchd interval.

Resolution (no flags needed in the common case):
  URL  : $SISO_BRAIN_URL  else if on the Mini -> http://127.0.0.1:8830
                          else                -> https://shaans-mac-mini.tail100d11.ts.net:8831
  TOKEN: $SISO_BRAIN_TOKEN  else first of ~/.siso/brain-tokens/{spawn,write,read}.token that exists

Run:  python3 voice-sync.py
"""
import json, os, socket, ssl, sys, urllib.request, urllib.error

HOME = os.path.expanduser("~")
OUTBOX = os.path.join(HOME, ".siso", "voice-outbox.ndjson")
DEADLETTER = os.path.join(HOME, ".siso", "voice-outbox.deadletter.ndjson")
ENDPOINT = "/voice/utterance"
MINI_HOSTNAMES = ("shaans-mac-mini", "Shaans-Mac-mini")


def _on_mini():
    h = socket.gethostname()
    return any(h.lower().startswith(m.lower()) for m in MINI_HOSTNAMES)


def _url():
    u = os.environ.get("SISO_BRAIN_URL")
    if u:
        return u.rstrip("/")
    return "http://127.0.0.1:8830" if _on_mini() else "https://shaans-mac-mini.tail100d11.ts.net:8831"


def _token():
    t = os.environ.get("SISO_BRAIN_TOKEN")
    if t:
        return t.strip()
    for tier in ("spawn", "write", "read"):
        p = os.path.join(HOME, ".siso", "brain-tokens", f"{tier}.token")
        if os.path.exists(p):
            with open(p) as f:
                return f.read().strip()
    return ""


def _deadletter(line):
    """Preserve a permanently-rejected or malformed line verbatim (never lost,
    never re-POSTed). A future replayer can re-drain this file after fixes."""
    with open(DEADLETTER, "a") as f:
        f.write(line + "\n")


def _post(body, timeout=10):
    """POST one utterance. Returns (code, resp); code is None if unreachable."""
    req = urllib.request.Request(_url() + ENDPOINT, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {_token()}")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")
    except Exception as e:
        return None, {"error": str(e), "unreachable": True}


def main():
    if not os.path.exists(OUTBOX):
        print(json.dumps({"drained": 0, "queued": 0, "errors": 0, "deadlettered": 0, "note": "no outbox"}))
        return

    lines = [l for l in open(OUTBOX).read().splitlines() if l.strip()]
    if not lines:
        print(json.dumps({"drained": 0, "queued": 0, "errors": 0, "deadlettered": 0}))
        return

    remaining, drained, errors, deadlettered = [], 0, 0, 0
    for l in lines:
        try:
            body = json.loads(l)
        except Exception:
            # malformed line — preserve it in the dead-letter, would never drain
            errors += 1
            deadlettered += 1
            _deadletter(l)
            continue
        code, resp = _post(body)
        if code is None and resp.get("unreachable"):
            # brain unreachable — keep the line, retry next run
            remaining.append(l)
        elif code is not None and code < 400:
            drained += 1
        elif code is not None and code < 500:
            # 4xx: the brain permanently rejects this payload shape — re-posting
            # it every run is the retry storm. Preserve verbatim, never re-POST.
            errors += 1
            deadlettered += 1
            _deadletter(l)
        else:
            # 5xx: server-side transient — keep for retry and count for visibility
            errors += 1
            remaining.append(l)

    # rewrite remaining lines back atomically (temp file + rename)
    if remaining:
        tmp = OUTBOX + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(remaining) + "\n")
        os.replace(tmp, OUTBOX)
    else:
        # nothing left — truncate to empty so the file stays but small.
        # Skip the write if it is ALREADY empty: under a WatchPaths trigger this
        # truncate is itself a file-change event, which re-fires the agent for a
        # guaranteed drained=0 run. Only rewrite when there is something to clear.
        try:
            already_empty = os.path.getsize(OUTBOX) == 0
        except OSError:
            already_empty = False
        if not already_empty:
            open(OUTBOX, "w").close()

    print(json.dumps({"drained": drained, "queued": len(remaining), "errors": errors, "deadlettered": deadlettered}))


if __name__ == "__main__":
    main()
