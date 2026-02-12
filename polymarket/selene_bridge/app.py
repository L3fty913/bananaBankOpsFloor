#!/usr/bin/env python3
import os
import time
import json
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Optional: OpenAI client (installed on VPS)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

DB_PATH = os.getenv("SELENE_DB_PATH", "/opt/polybot/rag/selene_chat.db")
RAG_SOURCES_DIR = Path(os.getenv("RAG_SOURCES_DIR", "/opt/polybot/rag_sources"))
MODEL = os.getenv("SELENE_MODEL", "gpt-5.3-codex")
PROMPT_FILE = os.getenv("SELENE_PROMPT_FILE", "/opt/polybot/selene_bridge/selene_system_prompt.txt")


def load_system_prompt() -> str:
    # Priority: explicit env var (compact) -> file -> fallback
    envp = os.getenv("SELENE_SYSTEM_PROMPT")
    if envp and envp.strip():
        return envp.strip()
    try:
        p = Path(PROMPT_FILE)
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return (
        "You are Selene, an expert Polymarket prediction-markets trader. "
        "You are steady, kind, and direct. Ask clarifying questions when needed."
    )

app = FastAPI()

INDEX = """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'/>
  <title>Morpheus Console — Caesar ↔ Selene</title>
  <style>
    body{background:#0b0f17;color:#d8e2ff;font-family:Inter,system-ui;margin:0;padding:0}
    header{padding:12px 16px;border-bottom:1px solid #24314f;background:#0f1524;position:sticky;top:0}
    .wrap{padding:12px;height:calc(100vh - 58px);box-sizing:border-box}
    .panel{height:100%;display:flex;flex-direction:column;background:#121a2b;border:1px solid #24314f;border-radius:12px;overflow:hidden}
    .title{padding:10px 12px;border-bottom:1px solid #24314f;font-weight:800;display:flex;justify-content:space-between;gap:12px;align-items:center}
    .pill{font-size:12px;color:#8fa4d9;padding:2px 8px;border:1px solid #24314f;border-radius:999px}
    .chat{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
    .msg{max-width:88%;padding:10px 12px;border-radius:12px;line-height:1.35;white-space:pre-wrap}
    .morpheus{align-self:flex-end;background:#1b2948;border:1px solid #304a86}
    .selene{align-self:flex-start;background:#0f1524;border:1px solid #24314f}
    .caesar{align-self:flex-start;background:#0f1e16;border:1px solid #1c5a3f}
    .meta{font-size:12px;color:#8fa4d9;margin-bottom:4px}
    .composer{display:flex;flex-direction:column;gap:8px;padding:10px;border-top:1px solid #24314f;background:#0f1524}
    textarea{width:100%;background:#0b0f17;color:#d8e2ff;border:1px solid #24314f;border-radius:10px;padding:10px;resize:none;height:58px;box-sizing:border-box}
    .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    select{background:#0b0f17;color:#d8e2ff;border:1px solid #24314f;border-radius:10px;padding:8px}
    button{background:#59a1ff;color:#07101f;border:0;border-radius:10px;padding:10px 12px;font-weight:800;cursor:pointer}
    button.secondary{background:#1b2948;color:#d8e2ff;border:1px solid #304a86}
    label{font-size:12px;color:#8fa4d9}
  </style>
</head>
<body>
<header>
  <div style='display:flex;align-items:center;justify-content:space-between;gap:12px'>
    <div>
      <div style='font-weight:900'>Morpheus Console</div>
      <div class='pill'>Single thread • Manual-approve Selene • Model: <span id='model'></span></div>
    </div>
    <div class='row'>
      <button class='secondary' onclick='refreshAll()'>Refresh</button>
    </div>
  </div>
</header>

<div class='wrap'>
  <div class='panel'>
    <div class='title'>
      <div>Caesar ↔ Selene (same thread)</div>
      <div class='pill'>Messages are appended + stored in RAG</div>
    </div>
    <div id='chat' class='chat'></div>
    <div class='composer'>
      <div class='row'>
        <div>
          <label>Send as</label><br/>
          <select id='author'>
            <option value='morpheus'>Morpheus</option>
            <option value='caesar'>Caesar (log only)</option>
          </select>
        </div>
        <div>
      </div>
      <textarea id='text' placeholder='Type message…'></textarea>
      <div class='row'>
        <button onclick='sendMsg()'>Send</button>
        <span class='pill'>Defaults: delivered to Selene + logged for Caesar</span>
        <span class='pill'>Type START to enable collaboration / STOP to pause</span>
      </div>
    </div>
  </div>
</div>

<script>
async function jget(u){const r=await fetch(u); return await r.json();}
function el(id){return document.getElementById(id)}
function cls(author){return author==='morpheus'?'morpheus':(author==='selene'?'selene':(author==='system'?'them':'caesar'))}
function render(rows){
  const chatEl = el('chat');
  chatEl.innerHTML='';
  for(const m of rows){
    const wrap=document.createElement('div');
    const meta=document.createElement('div'); meta.className='meta';
    meta.textContent = `${new Date(m.ts_utc*1000).toISOString()} • ${m.author}`;
    const box=document.createElement('div');
    box.className='msg ' + cls(m.author);
    box.textContent=m.content;
    wrap.appendChild(meta); wrap.appendChild(box);
    chatEl.appendChild(wrap);
  }
  chatEl.scrollTop=chatEl.scrollHeight;
}
async function refreshAll(){
  const info=await jget('/info');
  el('model').textContent = info.model;
  const h=await jget('/history?limit=250');
  render(h.rows);
}
async function sendMsg(){
  const content=el('text').value.trim();
  if(!content) return;
  const author=el('author').value;
  el('text').value='';
  await fetch('/send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({author, content})});
  await refreshAll();
}
refreshAll();
setInterval(refreshAll, 4000);
</script>
</body>
</html>
"""


def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts_utc INTEGER NOT NULL,
          thread TEXT NOT NULL,
          author TEXT NOT NULL,
          content TEXT NOT NULL
        )
        """
    )
    con.commit()
    return con


def log_msg(thread: str, author: str, content: str):
    con = db()
    con.execute(
        "INSERT INTO messages(ts_utc, thread, author, content) VALUES (?, ?, ?, ?)",
        (int(time.time()), thread, author, content),
    )
    con.commit()
    con.close()

    # also append to a RAG source file (simple, durable)
    RAG_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    p = RAG_SOURCES_DIR / f"bridge_{thread}.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{int(time.time())}] {author}: {content}\n")


def selene_reply(user_text: str) -> str:
    if OpenAI is None:
        return "(Selene bridge error: openai python package not installed on server)"

    # Use env var OPENAI_API_KEY; do not print it.
    client = OpenAI()

    # Build short context window from DB (last ~25 messages in selene thread)
    con = db()
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT author, content FROM messages WHERE thread='selene' ORDER BY id DESC LIMIT 25"
    ).fetchall()
    con.close()

    context = []
    for r in reversed(rows):
        role = "user" if r["author"] == "morpheus" else "assistant"
        context.append({"role": role, "content": r["content"]})

    # Responses API
    resp = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": load_system_prompt()},
            *context,
            {"role": "user", "content": user_text},
        ],
        max_output_tokens=700,
    )

    # Extract text
    out = []
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    out.append(c.text)
    return "\n".join(out).strip() or "(no response text)"


class SendReq(BaseModel):
    content: str


@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX


@app.get("/info")
def info():
    return JSONResponse({"model": MODEL})


@app.get("/history")
def history(limit: int = 250):
    con = db()
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT ts_utc, thread, author, content FROM messages WHERE thread='main' ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    con.close()
    out = [dict(r) for r in reversed(rows)]
    return JSONResponse({"rows": out})


class SendUnifiedReq(BaseModel):
    author: str  # morpheus|caesar
    content: str


COLLAB_FLAG = Path(os.getenv("COLLAB_FLAG", "/opt/polybot/selene_bridge/collab_enabled.flag"))
CAESAR_INBOX = Path(os.getenv("CAESAR_INBOX", "/opt/polybot/rag_sources/caesar_inbox.log"))


def enqueue_for_caesar(author: str, content: str):
    # Append-only inbox so Morpheus can deliver messages to Caesar from the UI.
    RAG_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with CAESAR_INBOX.open("a", encoding="utf-8") as f:
        f.write(f"[{int(time.time())}] {author}: {content}\n")


@app.post("/send")
def send(req: SendUnifiedReq):
    author = (req.author or "morpheus").strip().lower()
    content = (req.content or "").strip()
    if not content:
        return JSONResponse({"ok": False, "error": "empty"})
    if author not in ("morpheus", "caesar"):
        return JSONResponse({"ok": False, "error": "bad author"})

    # Commands
    if author == "morpheus" and content.upper() in ("START", "GO", "COLLAB_ON"):
        COLLAB_FLAG.write_text(str(int(time.time())), encoding="utf-8")
        log_msg("main", "system", "COLLAB_ENABLED")
        enqueue_for_caesar("system", "Morpheus enabled Caesar↔Selene collaboration (COLLAB_ENABLED).")
        return JSONResponse({"ok": True, "collab": True})

    if author == "morpheus" and content.upper() in ("STOP", "PAUSE", "COLLAB_OFF"):
        try:
            COLLAB_FLAG.unlink(missing_ok=True)
        except Exception:
            pass
        log_msg("main", "system", "COLLAB_DISABLED")
        enqueue_for_caesar("system", "Morpheus disabled collaboration (COLLAB_DISABLED).")
        return JSONResponse({"ok": True, "collab": False})

    # Always log into the single thread
    log_msg("main", author, content)
    enqueue_for_caesar(author, content)

    # Default behavior: deliver to Selene (manual approve is enforced by Morpheus using this UI)
    reply = selene_reply(content)
    log_msg("main", "selene", reply)

    # If collaboration enabled, also enqueue Selene reply for Caesar to act on
    if COLLAB_FLAG.exists():
        enqueue_for_caesar("selene", reply)

    return JSONResponse({"ok": True})
