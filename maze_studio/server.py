# -*- coding: utf-8 -*-
"""弹珠迷宫 DIY —— 本地 Web 服务。

    python server.py            # 默认 http://127.0.0.1:8000
    python server.py --port 9000 --open
"""
from __future__ import annotations

import argparse
import threading
import time
import traceback
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import maze_core as mc
import maze_render3d as mr

HERE = Path(__file__).resolve().parent
UI = HERE / "ui"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(UI), static_url_path="/static")
RENDER_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}


def _cfg() -> mc.Config:
    return mc.Config.from_dict(request.get_json(force=True, silent=True) or {})


def _balls(cfg: mc.Config):
    r = cfg.ball_d / 2
    z = cfg.floor_t + r + 0.02
    sx, sy = cfg.cell_center(*cfg.start)
    ex, ey = cfg.cell_center(*cfg.end)
    col = mr.hex_rgb("#3A3D42")
    return [((sx, sy, z), r, col), ((ex, ey, z), r, col)]


@app.get("/")
def index():
    return send_from_directory(UI, "index.html")


@app.get("/api/preset/classic")
def preset_classic():
    return jsonify(mc.classic().to_dict())


@app.post("/api/random")
def api_random():
    d = request.get_json(force=True, silent=True) or {}
    n = int(d.get("n", 8))
    cfg = mc.random_maze(n=max(4, min(12, n)), seed=d.get("seed"))
    return jsonify(cfg.to_dict())


@app.post("/api/check")
def api_check():
    cfg = _cfg()
    return jsonify(cfg.diagnose())


@app.post("/api/build")
def api_build():
    cfg = _cfg()
    stamp = time.strftime("%m%d_%H%M%S")
    name = f"maze_{stamp}_{uuid.uuid4().hex[:4]}"
    t0 = time.time()
    mesh = cfg.to_trimesh()
    stl = OUT / f"{name}.stl"
    mesh.export(stl)
    with RENDER_LOCK:
        png = OUT / f"{name}_3d.png"
        mr.still(mesh, _balls(cfg), png, w=1100, h=820, elev=34, fill=0.86)
    return jsonify({
        "stl": f"/files/{stl.name}",
        "png": f"/files/{png.name}",
        "stats": {
            "triangles": int(len(mesh.faces)),
            "watertight": bool(mesh.is_watertight),
            "volume_cm3": round(float(mesh.volume) / 1000, 1),
            "grams": round(float(mesh.volume) / 1000 * 1.24 * 0.35, 0),
            "bbox": [round(float(v), 2) for v in (mesh.bounds[1] - mesh.bounds[0])],
            "seconds": round(time.time() - t0, 1),
        },
        "check": cfg.diagnose(),
    })


def _gif_job(job_id: str, cfg: mc.Config, opts: dict):
    try:
        mesh = cfg.to_trimesh()
        out = OUT / f"{job_id}.gif"

        def prog(p):
            JOBS[job_id]["progress"] = round(p * 100, 1)

        with RENDER_LOCK:
            mr.orbit(mesh, _balls(cfg), out,
                     frames=int(opts.get("frames", 72)),
                     w=960, h=720,
                     elev=float(opts.get("elev", 34)),
                     color=opts.get("color", "#F0872A"),
                     edge=opts.get("edge", "#5A3410"),
                     fps=int(opts.get("fps", 20)),
                     gif_px=int(opts.get("gif_px", 720)),
                     progress=prog)
        JOBS[job_id].update(status="done", progress=100,
                            url=f"/files/{out.name}",
                            mb=round(out.stat().st_size / 1e6, 1))
    except Exception:                                   # noqa: BLE001
        JOBS[job_id].update(status="error", error=traceback.format_exc(limit=3))


@app.post("/api/gif")
def api_gif():
    cfg = _cfg()
    opts = request.get_json(force=True, silent=True).get("opts", {})
    job_id = f"orbit_{time.strftime('%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    JOBS[job_id] = {"status": "running", "progress": 0}
    threading.Thread(target=_gif_job, args=(job_id, cfg, opts), daemon=True).start()
    return jsonify({"job": job_id})


@app.get("/api/job/<job_id>")
def api_job(job_id):
    return jsonify(JOBS.get(job_id, {"status": "unknown"}))


@app.get("/files/<path:name>")
def files(name):
    return send_from_directory(OUT, name, as_attachment=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    print(f"弹珠迷宫 DIY  ->  {url}")
    if a.open:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=a.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
