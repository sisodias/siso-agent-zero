#!/usr/bin/env python3
"""
voiced — voice-over-herdr web server. Sits ON TOP of herdr.

Serves a phone-friendly web page (mic button + chat view). When you speak:
  browser STT -> POST /say {text} -> `herdr pane run <orchestrator_pane>` ->
  poll `herdr pane read` -> show the agent's reply.

The orchestrator agent in the herdr pane IS the brain — it already knows how to
drive the whole system. This server is just the mouth + eyes over herdr.

Runs on the Mini; exposed to the tailnet via `tailscale serve` (same recipe as ttyd/braind).

Env:
  VOICED_PORT        (default 8842)
  HERDR_PANE         the pane id of the orchestrator agent to talk to (e.g. "1-1")
                     if unset, /say resolves the first agent in HERDR_WORKSPACE
  HERDR_WORKSPACE    (default 1)
  HERDR_BIN          (default ~/.local/bin/herdr)
"""
import json, os, re, subprocess, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.path.expanduser("~")
PORT = int(os.environ.get("VOICED_PORT", "8842"))
HERDR = os.environ.get("HERDR_BIN", f"{HOME}/.local/bin/herdr")
WS = os.environ.get("HERDR_WORKSPACE", "1")
PANE = os.environ.get("HERDR_PANE", "")


def herdr(*args, text=False):
    try:
        r = subprocess.run([HERDR, *args], capture_output=True, text=True, timeout=20)
        out = r.stdout.strip()
        return out if text else (json.loads(out) if out else {})
    except Exception as e:
        return {"error": str(e)} if not text else f"error: {e}"


def resolve_pane():
    """Use configured pane, else the first agent pane in the workspace."""
    if PANE:
        return PANE
    data = herdr("pane", "list")
    panes = data.get("result", {}).get("panes", []) if isinstance(data, dict) else []
    for p in panes:
        if p.get("agent") or p.get("agent_status"):
            return p.get("pane_id")
    return panes[0].get("pane_id") if panes else None


PAGE = """<!DOCTYPE html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Talk to JARVIS</title>
<style>
*{box-sizing:border-box} body{margin:0;background:#0b0e14;color:#e6edf3;font:16px/1.5 -apple-system,system-ui,sans-serif;height:100vh;display:flex;flex-direction:column}
header{padding:1em;text-align:center;border-bottom:1px solid #1f2733}
header b{color:#6fb3ff} .mut{color:#8b98a9;font-size:.8em}
#log{flex:1;overflow-y:auto;padding:1em;display:flex;flex-direction:column;gap:.6em}
.msg{max-width:85%;padding:.6em .9em;border-radius:14px;white-space:pre-wrap;word-wrap:break-word}
.you{align-self:flex-end;background:#1d4ed8;color:#fff} .az{align-self:flex-start;background:#1a2230}
.sys{align-self:center;color:#8b98a9;font-size:.8em}
footer{padding:1em;border-top:1px solid #1f2733;display:flex;gap:.6em;align-items:center}
#mic{flex:0 0 auto;width:64px;height:64px;border-radius:50%;border:none;background:#1d4ed8;color:#fff;font-size:1.6em;cursor:pointer}
#mic.rec{background:#dc2626;animation:p 1s infinite} @keyframes p{50%{opacity:.5}}
#txt{flex:1;background:#141925;border:1px solid #26303f;color:#e6edf3;border-radius:12px;padding:.7em;font:inherit}
button.send{background:#1a2230;border:1px solid #26303f;color:#6fb3ff;border-radius:12px;padding:.7em 1em}
</style></head><body>
<header><b>JARVIS</b> <span class=mut id=target>talking to herdr</span></header>
<div id=log><div class="msg sys">Tap the mic and talk. Your words go to the orchestrator agent in herdr.</div></div>
<footer>
  <button id=mic title="hold to talk">🎤</button>
  <input id=txt placeholder="or type…" autocomplete=off>
  <button class=send id=send>➤</button>
</footer>
<script>
const log=document.getElementById('log'), mic=document.getElementById('mic'), txt=document.getElementById('txt');
function add(cls,t){const d=document.createElement('div');d.className='msg '+cls;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
async function send(text){
  if(!text||!text.trim())return; add('you',text); txt.value='';
  const thinking=add('az','…');
  try{
    const r=await fetch('/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
    const j=await r.json(); thinking.textContent = j.reply || j.error || '(no reply)';
  }catch(e){ thinking.textContent='error: '+e; }
}
document.getElementById('send').onclick=()=>send(txt.value);
txt.addEventListener('keydown',e=>{if(e.key==='Enter')send(txt.value);});
// browser-native speech recognition (Safari/Chrome over HTTPS)
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){
  const rec=new SR(); rec.lang='en-US'; rec.interimResults=false;
  let listening=false;
  mic.onclick=()=>{ if(listening){rec.stop();return;} rec.start(); };
  rec.onstart=()=>{listening=true;mic.classList.add('rec');};
  rec.onend=()=>{listening=false;mic.classList.remove('rec');};
  rec.onresult=e=>{ const t=e.results[0][0].transcript; send(t); };
  rec.onerror=e=>{ add('sys','mic: '+e.error); };
}else{ mic.onclick=()=>add('sys','Voice not supported here — type instead.'); }
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else (json.dumps(body).encode() if ctype == "application/json" else body.encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/health":
            return self._send(200, {"ok": True, "pane": resolve_pane()})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/say":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", "0") or "0")
        body = json.loads(self.rfile.read(n).decode() or "{}")
        text = (body.get("text") or "").strip()
        if not text:
            return self._send(400, {"error": "empty"})
        pane = resolve_pane()
        if not pane:
            return self._send(503, {"error": "no herdr pane / agent found"})
        # snapshot the pane before, send the text, then read what's new
        before = herdr("pane", "read", pane, "--source", "recent", "--lines", "200", text=True)
        herdr("pane", "run", pane, text)
        # poll for the agent to produce output (up to ~40s)
        reply = ""
        for _ in range(20):
            time.sleep(2)
            after = herdr("pane", "read", pane, "--source", "recent", "--lines", "200", text=True)
            if after and after != before:
                # crude diff: take lines in `after` not in `before`'s tail
                new = after[len(before):] if after.startswith(before[:200]) else after
                reply = _clean(new) or _clean(after[-1200:])
                # if the agent looks idle/done, stop early
                if reply and ("\n" in reply):
                    break
        return self._send(200, {"reply": reply or "(sent — agent is working; check the herdr tab)", "pane": pane})

    def log_message(self, *a):
        pass


def _clean(s):
    if not s:
        return ""
    s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)         # ANSI
    s = re.sub(r"[│┌┐└┘─╭╮╰╯]", "", s)                    # box chars
    lines = [l.rstrip() for l in s.splitlines() if l.strip()]
    return "\n".join(lines[-12:]).strip()


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"voiced on 127.0.0.1:{PORT} | herdr={HERDR} ws={WS} pane={PANE or '(auto)'}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
