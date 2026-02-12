#!/usr/bin/env python3
import os
import json
import time
import sqlite3
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

DB_PATH = os.getenv("EQUITY_DB_PATH", "/opt/polybot/rag/equity_terminal.db")
app = FastAPI()

INDEX = """
<!doctype html><html><head><meta charset='utf-8'/><title>Morpheus Equity Terminal</title>
<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
<style>body{background:#0b0f17;color:#d8e2ff;font-family:Inter,system-ui;margin:0;padding:16px} .row{display:flex;gap:18px;flex-wrap:wrap} .card{background:#121a2b;border:1px solid #24314f;border-radius:10px;padding:12px 14px;min-width:180px} .big{font-size:28px;font-weight:700} .muted{color:#8fa4d9} #stale{color:#ffbf69;font-weight:600} canvas{background:#0f1524;border:1px solid #24314f;border-radius:12px;padding:8px} button{background:#1b2948;color:#d8e2ff;border:1px solid #304a86;border-radius:8px;padding:6px 10px;margin-right:6px}</style>
</head><body>
<h2>Equity-Only Terminal</h2>
<div class='row'>
  <div class='card'><div class='muted'>Current Equity</div><div id='eq' class='big'>-</div></div>
  <div class='card'><div class='muted'>Session Change</div><div id='sess' class='big'>-</div></div>
  <div class='card'><div class='muted'>24h Change</div><div id='d24' class='big'>-</div></div>
  <div class='card'><div class='muted'>Max Drawdown (session)</div><div id='mdd' class='big'>-</div></div>
  <div class='card'><div class='muted'>High Water Mark</div><div id='hwm' class='big'>-</div></div>
</div>
<div style='margin:12px 0'><button onclick="setTf('1h')">1h</button><button onclick="setTf('6h')">6h</button><button onclick="setTf('24h')">24h</button><button onclick="setTf('7d')">7d</button><button onclick="setTf('all')">All</button><span id='stale'></span></div>
<canvas id='c' height='120'></canvas>
<script>
let tf='6h';
const ctx=document.getElementById('c');
const chart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{label:'Equity',data:[],borderColor:'#59a1ff',pointRadius:0,tension:0.18}]},options:{animation:false,responsive:true,plugins:{legend:{display:false},tooltip:{enabled:true}},scales:{x:{ticks:{color:'#8fa4d9'}},y:{ticks:{color:'#8fa4d9'}}}}});
function fmt(x){return '$'+Number(x).toFixed(2)}
function pct(a,b){if(!a||a===0)return 0; return ((b-a)/a*100)}
function setTf(v){tf=v; loadHistory();}
async function loadHistory(){
  const r=await fetch('/history?tf='+tf); const j=await r.json(); render(j.rows);}
function render(rows){
  if(!rows.length)return;
  chart.data.labels=rows.map(r=>r.timestamp_et);
  chart.data.datasets[0].data=rows.map(r=>r.equity_total_usd);
  chart.update('none');
  const cur=rows[rows.length-1].equity_total_usd;
  const start=rows[0].equity_total_usd;
  const last24 = rows.find(r=> (rows[rows.length-1].ts_utc - r.ts_utc) <= 86400 ) || rows[0];
  const d24Base = last24.equity_total_usd;
  let hwm=rows[0].equity_total_usd, mdd=0;
  for(const r of rows){hwm=Math.max(hwm,r.equity_total_usd); mdd=Math.min(mdd,(r.equity_total_usd-hwm));}
  document.getElementById('eq').innerText=fmt(cur);
  document.getElementById('sess').innerText=`${fmt(cur-start)} (${pct(start,cur).toFixed(2)}%)`;
  document.getElementById('d24').innerText=`${fmt(cur-d24Base)} (${pct(d24Base,cur).toFixed(2)}%)`;
  document.getElementById('mdd').innerText=fmt(mdd);
  document.getElementById('hwm').innerText=fmt(Math.max(...rows.map(r=>r.equity_total_usd)));
  const st=rows[rows.length-1].stale_data; document.getElementById('stale').innerText=st? 'STALE DATA':'';
}
const es=new EventSource('/stream');
es.onmessage=(ev)=>{const snap=JSON.parse(ev.data); if(!window.buf) window.buf=[]; window.buf.push(snap); if(window.buf.length>2000) window.buf.shift(); render(window.buf);} 
loadHistory();
</script></body></html>
"""


def q(sql, args=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, args).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX

@app.get("/history")
def history(tf: str = "6h"):
    now = int(time.time())
    if tf == "1h":
        start = now - 3600
    elif tf == "6h":
        start = now - 6 * 3600
    elif tf == "24h":
        start = now - 24 * 3600
    elif tf == "7d":
        start = now - 7 * 24 * 3600
    else:
        start = 0
    rows = q("SELECT ts_utc,timestamp_et,equity_total_usd,stale_data FROM equity_snapshots WHERE ts_utc>=? ORDER BY ts_utc", (start,))
    return JSONResponse({"rows": rows})

@app.get("/stream")
def stream():
    def gen():
        last_id = 0
        while True:
            rows = q("SELECT id,ts_utc,timestamp_et,equity_total_usd,stale_data FROM equity_snapshots WHERE id>? ORDER BY id", (last_id,))
            for r in rows:
                last_id = r["id"]
                yield f"data: {json.dumps(r)}\n\n"
            time.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")
