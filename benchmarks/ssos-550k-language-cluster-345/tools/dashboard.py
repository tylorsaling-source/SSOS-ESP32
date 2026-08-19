from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "host-reference"
CHECKPOINTS = ROOT / "checkpoints"
DEFAULT_RUN_LOG = RESULTS / "train-real-00000001-to-00010000.jsonl"
DEFAULT_ERROR_LOG = RESULTS / "train-real-00000001-to-00010000.err.txt"
PID_FILE = RESULTS / "active-run.pid"
ACTIVE_RUN = RESULTS / "active-run.json"


def process_running(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes

        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        try:
            exit_code = ctypes.c_ulong()
            return bool(ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(exit_code))) and exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def state() -> dict:
    active = json.loads(ACTIVE_RUN.read_text(encoding="utf-8")) if ACTIVE_RUN.exists() else {}
    run_log = RESULTS / active.get("log", DEFAULT_RUN_LOG.name)
    error_log = RESULTS / active.get("error_log", DEFAULT_ERROR_LOG.name)
    target_steps = int(active.get("target_steps", 10_000))
    steps = []
    validations = []
    if run_log.exists():
        for line in run_log.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "step":
                steps.append(event)
            elif event.get("event") == "validation":
                validations.append(event)
    pid = int(PID_FILE.read_text().strip()) if PID_FILE.exists() else None
    latest = steps[-1] if steps else {}
    latest_validation = validations[-1] if validations else {}
    checkpoints = [
        {"name": path.name, "bytes": path.stat().st_size, "mtime": path.stat().st_mtime}
        for path in sorted(CHECKPOINTS.glob("step-*.pt"))
    ]
    quality_path = RESULTS / "quality-latest.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else None
    return {
        "format": "ssos.language.dashboard.v1",
        "running": process_running(pid),
        "pid": pid,
        "target_steps": target_steps,
        "step": latest.get("step", 0),
        "progress": latest.get("step", 0) / target_steps,
        "train_loss": latest.get("loss"),
        "gradient_norm": latest.get("grad_norm"),
        "boundary_gradient_norm": latest.get("boundary_grad_norm"),
        "learning_rate": latest.get("learning_rate"),
        "presented_tokens": latest.get("presented_tokens"),
        "tokens_per_parameter": latest.get("tokens_per_parameter"),
        "corpus_passes": latest.get("corpus_passes"),
        "validation_step": latest_validation.get("step"),
        "validation_loss": latest_validation.get("loss"),
        "validation_history": validations,
        "recent_training": steps[-120:],
        "checkpoints": checkpoints[-12:],
        "error_bytes": error_log.stat().st_size if error_log.exists() else 0,
        "quality": quality,
    }


HTML = r'''<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SSOS 550k training</title>
<style>
:root{color-scheme:light;--ink:#15211b;--muted:#647169;--line:#d7e0da;--paper:#f4f6f2;--card:#fff;--teal:#087f73;--blue:#2463a8;--amber:#b66a10}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:1180px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:center}.title{font-size:26px;font-weight:750}.sub{color:var(--muted);margin-top:4px}.pill{padding:7px 11px;border-radius:999px;background:#e8eee9;font-weight:700}.pill.live{background:#d9f3ea;color:#086347}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 3px 14px #233c2b0b}.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.value{font-size:27px;font-weight:760;margin-top:7px}.wide{grid-column:span 2}.bar{height:12px;background:#e5ebe7;border-radius:8px;overflow:hidden;margin-top:12px}.fill{height:100%;background:linear-gradient(90deg,var(--teal),#23aa91)}canvas{width:100%;height:230px;margin-top:12px}.rows{display:grid;grid-template-columns:1.3fr .7fr;gap:12px}.checkpoints{max-height:255px;overflow:auto}.cp{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:9px 0;font-variant-numeric:tabular-nums}.quality pre{white-space:pre-wrap;background:#f7f8f5;border-radius:10px;padding:12px}.warn{color:#9a570a}.ok{color:#08704f}@media(max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}.rows{grid-template-columns:1fr}.wide{grid-column:span 2}.wrap{padding:15px}}
</style></head><body><main class="wrap">
<div class="top"><div><div class="title">SSOS 550k language training</div><div class="sub">Adult language · split master/worker reference · 549,984 parameters</div></div><div id="status" class="pill">Loading</div></div>
<section class="grid">
 <div class="card wide"><div class="label">Progress</div><div id="progress" class="value">—</div><div class="bar"><div id="fill" class="fill"></div></div></div>
 <div class="card"><div class="label">Training loss</div><div id="train" class="value">—</div></div>
 <div class="card"><div class="label">Held-out loss</div><div id="val" class="value">—</div></div>
 <div class="card"><div class="label">Boundary gradient</div><div id="boundary" class="value">—</div></div>
 <div class="card"><div class="label">Gradient norm</div><div id="grad" class="value">—</div></div>
 <div class="card"><div class="label">Errors</div><div id="errors" class="value">—</div></div>
 <div class="card"><div class="label">Latest checkpoint</div><div id="checkpoint" class="value" style="font-size:18px">—</div></div>
 <div class="card"><div class="label">Tokens / parameter</div><div id="tpp" class="value">—</div></div>
 <div class="card"><div class="label">Corpus passes</div><div id="passes" class="value">—</div></div>
 <div class="card"><div class="label">Learning rate</div><div id="lr" class="value" style="font-size:20px">—</div></div>
</section>
<section class="rows"><div class="card"><div class="label">Loss curves</div><canvas id="chart" width="760" height="230"></canvas></div><div class="card checkpoints"><div class="label">Checkpoints</div><div id="cps"></div></div></section>
<section class="card quality" style="margin-top:12px"><div class="label">Language quality gate</div><div id="quality" class="sub">Samples run at evaluation milestones; loss alone is not acceptance.</div></section>
</main><script>
const $=id=>document.getElementById(id), fmt=x=>x==null?'—':Number(x).toFixed(3);
function chart(s){const c=$('chart'),x=c.getContext('2d'),w=c.width,h=c.height;x.clearRect(0,0,w,h);x.strokeStyle='#d7e0da';x.lineWidth=1;for(let i=0;i<5;i++){let y=18+i*(h-36)/4;x.beginPath();x.moveTo(36,y);x.lineTo(w-12,y);x.stroke()}const all=[...(s.recent_training||[]).map(v=>v.loss),...(s.validation_history||[]).map(v=>v.loss)].filter(Number.isFinite);if(!all.length)return;let lo=Math.min(...all),hi=Math.max(...all);if(hi-lo<.1)hi=lo+.1;function draw(a,color,key){if(a.length<2)return;x.strokeStyle=color;x.lineWidth=3;x.beginPath();a.forEach((v,i)=>{let px=36+(w-52)*(v.step/s.target_steps),py=18+(h-36)*(1-(v[key]-lo)/(hi-lo));i?x.lineTo(px,py):x.moveTo(px,py)});x.stroke()}draw(s.recent_training||[],'#087f73','loss');draw(s.validation_history||[],'#2463a8','loss')}
async function update(){try{let s=await fetch('/api/state',{cache:'no-store'}).then(r=>r.json());$('status').textContent=s.running?'Training live':'Stopped';$('status').className='pill '+(s.running?'live':'');$('progress').textContent=`${s.step.toLocaleString()} / ${s.target_steps.toLocaleString()} (${(s.progress*100).toFixed(1)}%)`;$('fill').style.width=(s.progress*100)+'%';$('train').textContent=fmt(s.train_loss);$('val').textContent=fmt(s.validation_loss);$('boundary').textContent=fmt(s.boundary_gradient_norm);$('grad').textContent=fmt(s.gradient_norm);$('tpp').textContent=fmt(s.tokens_per_parameter);$('passes').textContent=fmt(s.corpus_passes);$('lr').textContent=s.learning_rate==null?'—':Number(s.learning_rate).toExponential(2);$('errors').textContent=s.error_bytes===0?'None':s.error_bytes+' bytes';$('errors').className='value '+(s.error_bytes===0?'ok':'warn');let cp=s.checkpoints.at(-1);$('checkpoint').textContent=cp?cp.name:'—';$('cps').innerHTML=s.checkpoints.slice().reverse().map(v=>`<div class="cp"><span>${v.name}</span><span>${(v.bytes/1048576).toFixed(2)} MB</span></div>`).join('');$('quality').innerHTML=s.quality?`<pre>${JSON.stringify(s.quality,null,2)}</pre>`:'Samples run at evaluation milestones; loss alone is not acceptance.';chart(s)}catch(e){$('status').textContent='Dashboard error'}}update();setInterval(update,2000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            payload = json.dumps(state()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif path in ("/", "/index.html"):
            payload = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            payload = b"not found"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8241)
    args = parser.parse_args()
    print(json.dumps({"event": "dashboard_ready", "url": f"http://{args.host}:{args.port}/"}), flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
