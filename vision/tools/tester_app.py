"""Drop-an-image tester: http://127.0.0.1:8000

usage: python vision/tools/tester_app.py [--port 8000] [--host 127.0.0.1]

Drag one or more photos onto the page (or click / paste). No calibration needed: the dial, the
gauge type (its scale) and the lit lamps are found automatically. Each photo gets
NORMAL / ABNORMAL / CAN'T TELL with a confidence %, the reading and an annotated image.

Also an HTTP API for other programs (e.g. a server that receives camera photos):
    curl -F image=@photo.jpg http://127.0.0.1:8000/api/read            (scale recognised)
    curl -F image=@photo.jpg -F max=10 http://127.0.0.1:8000/api/read  (force 0-10 scale)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from o2gauge.auto import AutoReader, decide, draw          # noqa: E402
from o2gauge.config import MonitorConfig                    # noqa: E402
from o2gauge import postgres_store                            # noqa: E402
from o2gauge.postgres_api import api as postgres_api, verify_identity  # noqa: E402
from o2gauge.stage_b import KeypointReader                 # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
app.register_blueprint(postgres_api)
_reader: AutoReader | None = None
_lock = threading.Lock()
_jobs_stop = threading.Event()


def _scheduled_jobs() -> None:
    escalation_after = max(30, int(os.getenv("ALERT_ESCALATION_AFTER_S", "120")))
    heartbeat_s = max(5, int(os.getenv("DEVICE_HEARTBEAT_S", "30")))
    while not _jobs_stop.wait(10):
        try:
            events = postgres_store.run_scheduled_jobs(
                escalation_after_s=escalation_after, heartbeat_s=heartbeat_s,
                missed_heartbeats=2, grace_s=5,
            )
            # Alert state and escalation are persisted for clients polling PostgreSQL.
        except Exception as exc:
            print(f"PostgreSQL alert scheduler error: {exc}")


def reader() -> AutoReader:
    global _reader
    if _reader is None:
        panel = ROOT / "vision/models/gauge_pose_panel.onnx"        # specialist for the hospital panels
        _reader = AutoReader(KeypointReader(ROOT / "vision/models/gauge_pose.onnx"), read_text=True,
                             panel_model=KeypointReader(panel) if panel.exists() else None)
    return _reader


@app.post("/api/read")
def api_read():
    device_id = request.form.get("device_id", "").strip()
    identity = None
    if device_id:
        try:
            identity = verify_identity(request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
            if identity.get("role") not in ("staff", "admin"):
                return jsonify(error="This account does not have staff access."), 403
            gauge_rows = postgres_store.get_device_gauges(identity, device_id)
            gauge_config = {g["number"]: {
                "number": g["number"], "low_threshold": g["low_threshold"],
                "critical_threshold": g["critical_threshold"], "ignored": g["ignored"],
            } for g in gauge_rows}
        except PermissionError as exc:
            return jsonify(error=str(exc)), 401
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except postgres_store.StoreUnavailable as exc:
            return jsonify(error=str(exc)), 503
    else:
        gauge_config = None
    f = request.files.get("image")
    if f is None:
        return jsonify(error="send the photo as multipart field 'image'"), 400
    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify(error="not an image (use JPG or PNG)"), 400
    mx = request.form.get("max", "").strip()
    try:
        max_value = float(mx) if mx and mx.lower() != "auto" else None
    except ValueError:
        return jsonify(error=f"max must be a number or 'auto', got {mx!r}"), 400
    if gauge_config is None:
        try:
            posted_gauges = json.loads(request.form.get("gauges", "[]"))
            if not isinstance(posted_gauges, list) or len(posted_gauges) > 12:
                raise ValueError("gauges must be a list with at most 12 entries")
            gauge_config = {int(g["number"]): g for g in posted_gauges if isinstance(g, dict) and "number" in g}
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return jsonify(error=f"invalid gauge configuration: {exc}"), 400
    include_image = request.form.get("include_image", "never")
    if include_image not in ("never", "always", "on_alert"):
        return jsonify(error="include_image must be never, always, or on_alert"), 400
    t0 = time.perf_counter()
    with _lock:
        r = reader().read(img, max_value)
        if gauge_config:
            selected = []
            for g in r["readings"]:
                saved = gauge_config.get(g.number)
                if saved is None or saved.get("ignored"):
                    continue
                if saved and g.value is not None and g.status != "UNCERTAIN":
                    low = float(saved.get("low_threshold", reader().cfg.low_threshold))
                    critical = float(saved.get("critical_threshold", reader().cfg.critical_threshold))
                    if critical >= low:
                        return jsonify(error=f"gauge {g.number}: Critical threshold must be below Low"), 400
                    g.low_limit = low
                    g.critical_threshold = critical
                    g.status = "CRITICAL" if g.value < critical else "LOW" if g.value < low else "OK"
                selected.append(g)
            r["readings"] = selected
            r["main"] = selected[0] if selected else None
            main_config = reader().cfg
            if r["main"] is not None and r["main"].low_limit is not None:
                main_config = MonitorConfig.from_dict({
                    **main_config.to_dict(), "low_threshold": r["main"].low_limit,
                })
            r["verdict"] = decide(r["main"], r["lamps"], main_config)
    ms = (time.perf_counter() - t0) * 1000
    v, m = r["verdict"], r["main"]
    alert = v.verdict == "ABNORMAL" or any(g.status in ("LOW", "CRITICAL") for g in r["readings"])
    payload = dict(
        file=f.filename,
        verdict="ABNORMAL" if alert else v.verdict,
        alert=alert,
        confidence_pct=round(v.confidence * 100),
        reasons=v.reasons,
        reading=None if m is None or m.value is None else round(m.value, 2),
        unit=None if m is None else (m.cal.unit if m.cal is not None else m.unit) or None,
        reading_confidence_pct=None if m is None else round(m.confidence * 100),
        classical=None if m is None else m.stage_a,
        model=None if m is None else m.stage_b,
        gauge_type=None if m is None else m.gauge_type,
        scale=None if m is None else m.scale,
        low_limit=(m.low_limit if m is not None and m.low_limit is not None else reader().cfg.low_threshold),
        main_gauge=None if m is None else m.number,
        gas=None if m is None else m.gas,
        gauges=[{"number": g.number, "gas": g.gas, "reading": None if g.value is None else round(g.value, 3),
                 "unit": g.unit, "scale": g.scale, "scale_source": g.scale_source, "secondary": g.secondary,
                 "confidence_pct": round(g.confidence * 100), "status": g.status, "main": g is m, "kind": g.kind,
                 "numbers_read": [] if g.text is None else [b.text for b in g.text.boxes if b.num is not None],
                 "low_threshold": g.low_limit, "critical_threshold": getattr(g, "critical_threshold", None),
                 "ignored": False}
                for g in sorted(r["readings"], key=lambda g: g.number)],
        other_dials=[{"reading": g.value, "type": g.gauge_type, "gas": g.gas, "unit": g.unit}
                     for g in r["readings"][1:]],
        lamps=[{"color": l.color, "strength": l.strength} for l in r["lamps"]],
        ms=round(ms),
    )
    if include_image == "always" or (include_image == "on_alert" and alert):
        ann = draw(img, r)
        h, w = ann.shape[:2]
        if w > 1400:
            ann = cv2.resize(ann, (1400, int(h * 1400 / w)), interpolation=cv2.INTER_AREA)
        payload["image"] = "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", ann, [cv2.IMWRITE_JPEG_QUALITY, 75])[1]).decode()
    if device_id and identity:
        try:
            events = postgres_store.persist_reading(identity, device_id, payload)
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except (ValueError, postgres_store.StoreUnavailable) as exc:
            return jsonify(error=str(exc)), 503
        if events:
            payload["alert_id"] = next((event["id"] for event in events if event.get("state") == "OPEN"), None)
    return jsonify(payload)


@app.get("/api/health")
def api_health():
    """Lightweight endpoint for checking that a mobile client can reach this server."""
    return jsonify(ok=True, service="o2-vision", postgres_configured=postgres_store.configured(),
                   postgres_ready=postgres_store.healthy())


@app.get("/")
def index():
    return PAGE


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gauge Tester</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2330;--mute:#5d6676;--line:#dfe3ea;--ok:#1e8e3e;--bad:#c5221f;--unk:#6b7280;--acc:#1a73e8}
@media (prefers-color-scheme:dark){:root{--bg:#111418;--card:#1b1f25;--ink:#e8eaed;--mute:#9aa0a6;--line:#2c323b;--acc:#8ab4f8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 16px}
.bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
select,button{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
#drop{border:2px dashed var(--line);border-radius:14px;padding:34px 16px;text-align:center;background:var(--card);cursor:pointer;transition:.15s}
#drop.over{border-color:var(--acc);background:color-mix(in srgb,var(--acc) 8%,var(--card))}
#drop b{font-size:17px}#drop small{display:block;color:var(--mute);margin-top:6px}
.res{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-top:16px;overflow:hidden}
.head{display:flex;align-items:center;gap:16px;padding:14px 16px;color:#fff;flex-wrap:wrap}
.head .v{font-size:26px;font-weight:800;letter-spacing:.5px}.head .f{opacity:.85;margin-left:auto;font-size:13px;word-break:break-all}
.NORMAL{background:var(--ok)}.ABNORMAL{background:var(--bad)}.CANT{background:var(--unk)}
.conf{flex:1;min-width:180px;max-width:320px}.conf .t{font-size:13px;opacity:.9}
.meter{height:10px;background:rgba(255,255,255,.3);border-radius:6px;overflow:hidden}.meter i{display:block;height:100%;background:#fff}
.body{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:16px;padding:16px}
@media (max-width:760px){.body{grid-template-columns:1fr}}
.body img{width:100%;border-radius:8px;border:1px solid var(--line)}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:0}dt{color:var(--mute)}dd{margin:0;font-variant-numeric:tabular-nums}
.big{font-size:30px;font-weight:700}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-size:13px;font-weight:600;margin:2px 4px 2px 0;color:#fff}
.green{background:#1e8e3e}.red{background:#c5221f}.amber{background:#e37400}
ul{margin:8px 0 0;padding-left:18px}li{margin:2px 0}
.note{color:var(--mute);font-size:13px;margin-top:10px}
.spin{padding:18px;color:var(--mute)}
table.g{width:100%;border-collapse:collapse;font-size:14px}table.g th,table.g td{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}
table.g th{color:var(--mute);font-weight:600}table.g tr.main td{font-weight:600}table.g .num{font-variant-numeric:tabular-nums;white-space:nowrap}
table.g small{color:var(--mute);font-weight:400}
</style></head><body><main>
<h1>Oxygen gauge tester</h1>
<p class="sub">Drop a panel photo. Needle dials, digital displays, gauge type and lamp colours are found automatically, from any reasonable camera angle, with no clicking.</p>
<div class="bar"><label>Scale&nbsp;<select id="max">
<option value="auto" selected>Auto (read the numbers on each dial)</option><option value="16">0 - 16 kg/cm² (alarm box)</option>
<option value="10.55">0 - 10.55 kg/cm² = 150 psi (Magnate)</option></select></label>
<button id="clear" type="button">Clear results</button></div>
<div id="drop" tabindex="0"><b>Drop photos here</b><small>or click to choose · or paste (Ctrl+V) · JPG / PNG · several at once is fine</small>
<input id="file" type="file" accept="image/*" multiple hidden></div>
<div id="out"></div>
<p class="note">Low-pressure limit is a placeholder until the hospital confirms it. Confidence combines the needle reading
(classical method + trained model, and how far from the limit it is) with the lamp colours. Any red / amber lamp, or a needle
below the limit, gives ABNORMAL. If they disagree it says so and the confidence drops.</p>
</main><script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),out=document.getElementById('out');
drop.onclick=()=>file.click();drop.onkeydown=e=>{if(e.key==='Enter'||e.key===' ')file.click()};
file.onchange=()=>send([...file.files]);
['dragenter','dragover'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add('over')}));
['dragleave','drop'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove('over')}));
drop.addEventListener('drop',e=>send([...e.dataTransfer.files]));
document.addEventListener('paste',e=>{const f=[...e.clipboardData.files];if(f.length)send(f)});
document.getElementById('clear').onclick=()=>out.innerHTML='';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function send(files){
  for(const f of files.filter(f=>f.type.startsWith('image/'))){
    const card=document.createElement('div');card.className='res';card.innerHTML='<div class="spin">Reading '+esc(f.name)+' …</div>';
    out.prepend(card);
    const fd=new FormData();fd.append('image',f);fd.append('max',document.getElementById('max').value);fd.append('include_image','always');
    try{const r=await fetch('/api/read',{method:'POST',body:fd});const j=await r.json();
      if(!r.ok)throw new Error(j.error||r.status);card.innerHTML=render(j,f.name)}
    catch(e){card.innerHTML='<div class="spin">'+esc(f.name)+': '+esc(e.message)+'</div>'}
  }
  file.value='';
}
function render(j,name){
  const cls=j.verdict==='NORMAL'?'NORMAL':j.verdict==='ABNORMAL'?'ABNORMAL':'CANT';
  const lamps=j.lamps.length?j.lamps.map(l=>`<span class="chip ${l.color}">${l.color.toUpperCase()}</span>`).join(''):'none lit';
  const rows=j.gauges.map(g=>`<tr${g.main?' class="main"':''}><td>#${g.number}${g.main?' ★':''}</td><td>${g.kind==='digital'?'<b>digital display</b>':esc(g.gas||'—')}</td>
   <td class="num">${g.reading??'--'} ${esc(g.unit||'')}${g.secondary?'<br><small>'+esc(g.secondary)+'</small>':''}</td>
   <td>${esc(g.scale)}</td><td class="num">${g.confidence_pct}%</td><td>${esc(g.status)}</td></tr>`).join('');
  const table=`<table class="g"><thead><tr><th>Dial</th><th>Gas</th><th>Reading</th><th>Scale</th><th>Conf.</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
  return `<div class="head ${cls}"><div class="v">${esc(j.verdict)}</div>
   <div class="conf"><div class="t">confidence ${j.confidence_pct}%</div><div class="meter"><i style="width:${j.confidence_pct}%"></i></div></div>
   <div class="f">${esc(name)} · ${j.ms} ms</div></div>
   <div class="body"><div><img src="${j.image}" alt="annotated result"></div><div>
   <div class="big">${j.reading??'--'} <small style="font-size:15px">${esc(j.unit||'')}</small></div>
   <div class="note" style="margin-top:0">main gauge${j.main_gauge?' #'+j.main_gauge:''}${j.gas?' · '+esc(j.gas):''}</div>
   <dl><dt>Reading conf.</dt><dd>${j.reading_confidence_pct??'--'}%</dd>
   <dt>Scale</dt><dd>${esc(j.scale||'not found')}</dd><dt>Lamps</dt><dd>${lamps}</dd></dl>
   <ul>${j.reasons.map(r=>'<li>'+esc(r)+'</li>').join('')}</ul></div></div>
   <div style="padding:0 16px 16px;overflow-x:auto">${table}</div>`;
}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    reader()                                     # load the model before the first request
    if postgres_store.configured():
        threading.Thread(target=_scheduled_jobs, daemon=True, name="postgres-alert-jobs").start()
    else:
        print("PostgreSQL is not configured; monitoring data will not be persisted.")
    print(f"Gauge tester ready: http://{a.host}:{a.port}")
    app.run(host=a.host, port=a.port, threaded=True)


if __name__ == "__main__":
    main()
