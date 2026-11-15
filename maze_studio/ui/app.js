/* 弹珠迷宫 DIY —— 前端 */
const $ = (s) => document.querySelector(s);
const canvas = $("#maze");
const ctx = canvas.getContext("2d");

const FIELDS = [
  ["n", "格数", 4, 12, 1],
  ["path_w", "路宽", 8, 30, 0.5],
  ["wall_t", "墙厚", 1.5, 8, 0.125],
  ["floor_t", "底板厚", 3, 15, 0.5],
  ["wall_h", "墙高", 10, 50, 1],
  ["ball_d", "弹珠直径", 5, 25, 0.5],
  ["hole_d", "格孔直径", 6, 30, 0.5],
  ["entry_d", "入口孔径", 6, 30, 0.5],
  ["entry_sill", "入口台阶", 0, 12, 0.5],
  ["exit_w", "出口方孔", 6, 30, 0.5],
];

const TOOL_HINT = {
  wall: "在格线上按住拖动 = 连续画墙；在已有墙上拖 = 擦除",
  hole: "点格子：无孔 → Ø16 → Ø18 → 无孔，循环切换",
  node: "点四格交点：加 / 去一个 Ø18 的大孔",
  move: "拖动任意孔到任意位置（不吸附到格子）；方向键微调 0.5mm，Shift 加速；双击归零，Delete 删除",
  start: "点一格设为起点 S（入口开在所选方向的边框上）",
  end: "点一格设为终点 T（出口开在所选方向的边框上）",
};

const state = {
  cfg: null,
  tool: "wall",
  check: null,
  hover: null,
  view: { s: 1, ox: 0, oy: 0, T: 1 },
  painting: null,
  sel: null,
  drag: null,
  busy: false,
  gifTimer: null,
};

/* ------------------------------------------------------------ 孔 */
function getHole(kind, idx) {
  return kind === "cell" ? state.cfg.holes[idx] : state.cfg.node_holes[idx];
}

function baseCenter(kind, h) {
  const c = state.cfg;
  return kind === "cell" ? cellCenter(c, h.r, h.c) : [h.i * pitch(c), h.j * pitch(c)];
}

function holeCenter(kind, h) {
  const [bx, by] = baseCenter(kind, h);
  return [bx + (h.dx || 0), by + (h.dy || 0)];
}

function hitHole(x, y) {
  const c = state.cfg;
  const cands = [];
  c.holes.forEach((h, idx) => cands.push(["cell", idx, h]));
  c.node_holes.forEach((h, idx) => cands.push(["node", idx, h]));
  let best = null;
  for (const [kind, idx, h] of cands) {
    const [cx, cy] = holeCenter(kind, h);
    const d = Math.hypot(x - cx, y - cy);
    const slack = h.d / 2 + 2.5;                    /* 允许点在孔边缘外一点点 */
    if (d <= slack && (!best || d < best.d)) best = { kind, idx, d, cx, cy };
  }
  return best;
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const r1 = (v) => Math.round(v * 10) / 10;

/* ------------------------------------------------------------ 几何 */
const pitch = (c) => c.path_w + c.wall_t;
const total = (c) => c.n * c.path_w + (c.n + 1) * c.wall_t;
const cellCenter = (c, r, k) => [k * pitch(c) + c.wall_t + c.path_w / 2,
                                 r * pitch(c) + c.wall_t + c.path_w / 2];

function blank(n) {
  const H = Array.from({ length: n + 1 }, (_, j) =>
    Array.from({ length: n }, () => (j === 0 || j === n ? 1 : 0)));
  const V = Array.from({ length: n }, (_, r) =>
    Array.from({ length: n + 1 }, (_, i) => (i === 0 || i === n ? 1 : 0)));
  return { H, V };
}

function resizeGrid(n) {
  const c = state.cfg;
  if (n === c.n) return;
  state.sel = null;
  const { H, V } = blank(n);
  for (let j = 0; j < Math.min(n + 1, c.H.length); j++)
    for (let k = 0; k < Math.min(n, c.H[j].length); k++) H[j][k] = c.H[j][k];
  for (let r = 0; r < Math.min(n, c.V.length); r++)
    for (let i = 0; i < Math.min(n + 1, c.V[r].length); i++) V[r][i] = c.V[r][i];
  c.n = n; c.H = H; c.V = V;
  c.holes = c.holes.filter((h) => h.r < n && h.c < n);
  c.node_holes = c.node_holes.filter((h) => h.j >= 1 && h.j <= n - 1 && h.i >= 1 && h.i <= n - 1);
  c.start = c.start.map((v) => Math.min(v, n - 1));
  c.end = c.end.map((v) => Math.min(v, n - 1));
}

function footprint(c) {
  const n = c.n, p = pitch(c), t = c.wall_t, out = [];
  for (let j = 0; j <= n; j++)
    for (let k = 0; k < n; k++)
      if (c.H[j][k]) out.push([k * p, j * p, p + t, t]);
  for (let r = 0; r < n; r++)
    for (let i = 0; i <= n; i++)
      if (c.V[r][i]) out.push([i * p, r * p, t, p + t]);
  return out;
}

/* ------------------------------------------------------------ 绘制 */
function addRoundRect(x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  addRoundRect(x, y, w, h, r);
}

function draw() {
  const c = state.cfg;
  if (!c) return;
  const T = total(c);
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 700, H = canvas.clientHeight || 700;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const pad = 30;
  const s = Math.min(W - 2 * pad, H - 2 * pad) / T;
  const ox = (W - T * s) / 2, oy = (H - T * s) / 2;
  state.view = { s, ox, oy, T };
  const X = (x) => ox + x * s, Y = (y) => oy + y * s;

  /* 板面 */
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,.6)";
  ctx.shadowBlur = 34;
  ctx.shadowOffsetY = 12;
  roundRect(ox, oy, T * s, T * s, 7);
  ctx.fillStyle = "#1c242d";
  ctx.fill();
  ctx.restore();

  /* 格线辅助 */
  ctx.strokeStyle = "rgba(255,255,255,.045)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i < c.n; i++) {
    const p = i * pitch(c);
    ctx.moveTo(X(p), Y(c.wall_t));
    ctx.lineTo(X(p), Y(T - c.wall_t));
    ctx.moveTo(X(c.wall_t), Y(p));
    ctx.lineTo(X(T - c.wall_t), Y(p));
  }
  ctx.stroke();

  /* 解法路径 */
  if (state.check && state.check.path && state.check.path.length > 1) {
    ctx.save();
    ctx.beginPath();
    state.check.path.forEach(([r, k], i) => {
      const [cx, cy] = cellCenter(c, r, k);
      i ? ctx.lineTo(X(cx), Y(cy)) : ctx.moveTo(X(cx), Y(cy));
    });
    ctx.strokeStyle = "rgba(63,185,80,.85)";
    ctx.lineWidth = Math.max(1.6, 2.2 * s / 6);
    ctx.setLineDash([6, 5]);
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.restore();
  }

  /* 墙体 */
  const rects = footprint(c);
  ctx.beginPath();
  for (const [x, y, w, h] of rects) {
    ctx.rect(X(x), Y(y), w * s, h * s);
  }
  ctx.fillStyle = "#f0872a";
  ctx.fill();

  /* 孔 */
  const holes = [];
  c.holes.forEach((h, idx) => {
    const [cx, cy] = holeCenter("cell", h);
    holes.push([cx, cy, h.d / 2, h.d, "cell", idx]);
  });
  c.node_holes.forEach((h, idx) => {
    const [cx, cy] = holeCenter("node", h);
    holes.push([cx, cy, h.d / 2, h.d, "node", idx]);
  });
  for (const [cx, cy, r, d, kind, idx] of holes) {
    if (state.sel && state.sel.kind === kind && state.sel.idx === idx) {
      ctx.beginPath();
      ctx.arc(X(cx), Y(cy), r * s + 5, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,255,255,.85)";
      ctx.lineWidth = 1.6;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const g = ctx.createRadialGradient(X(cx), Y(cy), r * s * 0.2, X(cx), Y(cy), r * s);
    g.addColorStop(0, "#7d211a");
    g.addColorStop(1, "#3a100d");
    ctx.beginPath();
    ctx.arc(X(cx), Y(cy), r * s, 0, Math.PI * 2);
    ctx.fillStyle = g;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,120,90,.5)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
    if (r * s > 11) {
      ctx.fillStyle = "rgba(255,220,210,.75)";
      ctx.font = `600 ${Math.min(12, r * s * 0.75)}px -apple-system, "Segoe UI", sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`Ø${d}`, X(cx), Y(cy));
    }
  }

  /* 拖动读数 */
  if (state.drag) {
    const h = getHole(state.drag.kind, state.drag.idx);
    const [cx, cy] = holeCenter(state.drag.kind, h);
    const sx = (h.dx || 0) >= 0 ? "+" : "";
    const sy = (h.dy || 0) >= 0 ? "+" : "";
    const txt = `Δ ${sx}${(h.dx || 0).toFixed(1)}, ${sy}${(h.dy || 0).toFixed(1)} mm`;
    ctx.font = '600 12px -apple-system, "Segoe UI", sans-serif';
    const tw = ctx.measureText(txt).width + 18;
    const bx = X(cx) - tw / 2;
    const by = Y(cy) + (h.d / 2) * s + 12;
    roundRect(bx, by, tw, 22, 6);
    ctx.fillStyle = "rgba(10,14,18,.92)";
    ctx.fill();
    ctx.strokeStyle = "rgba(240,135,42,.55)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#ffb066";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(txt, X(cx), by + 11);
  }

  /* S / T */
  drawMark(c, c.start, "S", "#3fb950", c.start_side);
  drawMark(c, c.end, "T", "#4aa3ff", c.end_side);

  /* 悬停高亮 */
  if (state.hover) {
    const hv = state.hover;
    ctx.fillStyle = "rgba(255,255,255,.22)";
    if (hv.kind === "H") {
      ctx.fillRect(X(hv.col * pitch(c)), Y(hv.j * pitch(c)),
                   pitch(c) * s, c.wall_t * s);
    } else if (hv.kind === "V") {
      ctx.fillRect(X(hv.i * pitch(c)), Y(hv.row * pitch(c)),
                   c.wall_t * s, pitch(c) * s);
    } else if (hv.kind === "cell") {
      const [cx, cy] = cellCenter(c, hv.r, hv.c);
      ctx.beginPath();
      ctx.arc(X(cx), Y(cy), c.path_w * s * 0.42, 0, Math.PI * 2);
      ctx.fill();
    } else if (hv.kind === "node") {
      ctx.beginPath();
      ctx.arc(X(hv.i * pitch(c)), Y(hv.j * pitch(c)), c.wall_t * s * 1.6, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  $("#dim-label").textContent =
    `${T.toFixed(1)} × ${T.toFixed(1)} × ${(c.floor_t + c.wall_h).toFixed(1)} mm`;
}

function drawMark(c, cell, letter, color, side) {
  const T = total(c);
  const [cx, cy] = cellCenter(c, cell[0], cell[1]);
  const X = (x) => state.view.ox + x * state.view.s;
  const Y = (y) => state.view.oy + y * state.view.s;
  const r = Math.min(c.path_w * 0.36, 13) * state.view.s;

  ctx.beginPath();
  ctx.arc(X(cx), Y(cy), r, 0, Math.PI * 2);
  ctx.fillStyle = color + "22";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.font = `700 ${Math.max(11, r * 0.95)}px -apple-system, "Segoe UI", sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(letter, X(cx), Y(cy));

  /* 边框上的开口箭头 */
  const t = c.wall_t;
  let ax = cx, ay = cy, dx = 0, dy = 0;
  if (side === "top") { ay = t; dy = 1; }
  if (side === "bottom") { ay = T - t; dy = -1; }
  if (side === "left") { ax = t; dx = 1; }
  if (side === "right") { ax = T - t; dx = -1; }
  const L = Math.max(7, c.path_w * 0.3);
  ctx.beginPath();
  ctx.moveTo(X(ax), Y(ay));
  ctx.lineTo(X(ax + dx * L), Y(ay + dy * L));
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  ctx.setLineDash([]);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(X(ax + dx * L), Y(ay + dy * L));
  ctx.lineTo(X(ax + dx * L - dx * 4 - dy * 4), Y(ay + dy * L - dy * 4 + dx * 4));
  ctx.lineTo(X(ax + dx * L - dx * 4 + dy * 4), Y(ay + dy * L - dy * 4 - dx * 4));
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

/* ------------------------------------------------------------ 命中 */
function boardPos(ev) {
  const rc = canvas.getBoundingClientRect();
  const px = ev.clientX - rc.left, py = ev.clientY - rc.top;
  const { s, ox, oy } = state.view;
  return [(px - ox) / s, (py - oy) / s, px, py];
}

function pick(ev) {
  const c = state.cfg;
  const [x, y, px, py] = boardPos(ev);
  const P = pitch(c), t = c.wall_t;
  const tolPx = 9 / state.view.s;

  if (state.tool === "wall") {
    let best = null;
    const jf = (y - t / 2) / P, j = Math.round(jf);
    if (j >= 0 && j <= c.n) {
      const d = Math.abs(y - (j * P + t / 2)) - t / 2;
      if (d <= tolPx) {
        const col = Math.max(0, Math.min(c.n - 1, Math.floor(x / P)));
        if (x > col * P - tolPx && x < (col + 1) * P + tolPx)
          best = { kind: "H", j, col, d };
      }
    }
    const if_ = (x - t / 2) / P, i = Math.round(if_);
    if (i >= 0 && i <= c.n) {
      const d = Math.abs(x - (i * P + t / 2)) - t / 2;
      if (d <= tolPx) {
        const row = Math.max(0, Math.min(c.n - 1, Math.floor(y / P)));
        if (y > row * P - tolPx && y < (row + 1) * P + tolPx)
          if (!best || d < best.d) best = { kind: "V", i, row, d };
      }
    }
    return best;
  }

  const col = Math.floor(x / P), row = Math.floor(y / P);
  if (col < 0 || col >= c.n || row < 0 || row >= c.n) return null;

  if (state.tool === "hole") return { kind: "cell", r: row, c: col };
  if (state.tool === "start") return { kind: "cell", r: row, c: col };
  if (state.tool === "end") return { kind: "cell", r: row, c: col };

  if (state.tool === "node") {
    const j = Math.round(y / P), i = Math.round(x / P);
    if (j < 1 || j > c.n - 1 || i < 1 || i > c.n - 1) return null;
    if (Math.hypot(x - i * P, y - j * P) > P * 0.5) return null;
    return { kind: "node", j, i };
  }
  return null;
}

function applyHit(hit, drag) {
  const c = state.cfg;
  if (!c || !hit) return false;

  if (hit.kind === "H" || hit.kind === "V") {
    const border = hit.kind === "H" ? (hit.j === 0 || hit.j === c.n)
                                    : (hit.i === 0 || hit.i === c.n);
    if (border) return false;                       /* 外框固定 */
    const arr = hit.kind === "H" ? c.H[hit.j] : c.V[hit.row];
    const idx = hit.kind === "H" ? hit.col : hit.i;
    let val;
    if (drag && state.painting) val = state.painting.val;
    else {
      val = arr[idx] ? 0 : 1;
      state.painting = { val };
    }
    if (arr[idx] === val) return false;
    arr[idx] = val;
    return true;
  }

  if (hit.kind === "cell") {
    if (state.tool === "start") { c.start = [hit.r, hit.c]; return true; }
    if (state.tool === "end") { c.end = [hit.r, hit.c]; return true; }
    if (state.tool === "hole") {
      const i = c.holes.findIndex((h) => h.r === hit.r && h.c === hit.c);
      if (i < 0) c.holes.push({ r: hit.r, c: hit.c, d: c.hole_d, dx: 0, dy: 0 });
      else if (c.holes[i].d < 17) c.holes[i].d = 18;
      else c.holes.splice(i, 1);
      return true;
    }
  }

  if (hit.kind === "node") {
    const i = c.node_holes.findIndex((h) => h.j === hit.j && h.i === hit.i);
    if (i < 0) c.node_holes.push({ j: hit.j, i: hit.i, d: 18, dx: 0, dy: 0 });
    else c.node_holes.splice(i, 1);
    return true;
  }
  return false;
}

/* ------------------------------------------------------------ 交互 */
function bind() {
  canvas.addEventListener("pointerdown", (ev) => {
    if (state.busy) return;
    canvas.setPointerCapture(ev.pointerId);

    if (state.tool === "move") {
      const [x, y] = boardPos(ev);
      const hit = hitHole(x, y);
      if (!hit) { state.sel = null; draw(); return; }
      const h = getHole(hit.kind, hit.idx);
      state.sel = { kind: hit.kind, idx: hit.idx };
      state.drag = {
        kind: hit.kind, idx: hit.idx, sx: x, sy: y,
        dx0: h.dx || 0, dy0: h.dy || 0, moved: false,
      };
      canvas.style.cursor = "grabbing";
      draw();
      return;
    }

    const hit = pick(ev);
    state.painting = null;
    if (applyHit(hit)) { draw(); scheduleCheck(); }
  });

  canvas.addEventListener("pointermove", (ev) => {
    if (state.drag) {
      const [x, y] = boardPos(ev);
      const h = getHole(state.drag.kind, state.drag.idx);
      if (!h) { state.drag = null; return; }
      const [bx, by] = baseCenter(state.drag.kind, h);
      const T = total(state.cfg);
      h.dx = r1(clamp(state.drag.dx0 + (x - state.drag.sx), -bx, T - bx));
      h.dy = r1(clamp(state.drag.dy0 + (y - state.drag.sy), -by, T - by));
      state.drag.moved = true;
      draw();
      return;
    }

    const hit = pick(ev);
    const changed = state.painting && hit &&
      (hit.kind === "H" || hit.kind === "V") && applyHit(hit, true);
    if (changed) { draw(); scheduleCheck(); }
    const sig = hit ? JSON.stringify(hit) : "";
    const old = state.hover ? JSON.stringify(state.hover) : "";
    if (sig !== old) { state.hover = hit; draw(); }
  });

  canvas.addEventListener("pointerup", () => {
    if (state.drag) {
      const moved = state.drag.moved;
      state.drag = null;
      canvas.style.cursor = state.tool === "move" ? "grab" : "crosshair";
      if (moved) scheduleCheck();
      draw();
      return;
    }
    state.painting = null;
  });

  canvas.addEventListener("pointerleave", () => {
    state.hover = null;
    state.painting = null;
    draw();
  });

  canvas.addEventListener("dblclick", (ev) => {
    if (state.tool !== "move") return;
    const [x, y] = boardPos(ev);
    const hit = hitHole(x, y);
    if (!hit) return;
    const h = getHole(hit.kind, hit.idx);
    h.dx = 0; h.dy = 0;
    draw();
    scheduleCheck();
  });

  document.querySelectorAll(".tool").forEach((b) => {
    b.addEventListener("click", () => {
      document.querySelectorAll(".tool").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.tool = b.dataset.tool;
      state.hover = null;
      if (state.tool !== "move") state.sel = null;
      $("#tool-hint").textContent = TOOL_HINT[state.tool];
      canvas.style.cursor = state.tool === "move" ? "grab"
        : state.tool === "wall" ? "crosshair" : "pointer";
      draw();
    });
  });

  $("#btn-classic").addEventListener("click", async () => {
    state.cfg = await fetch("/api/preset/classic").then((r) => r.json());
    syncInputs(); draw(); scheduleCheck();
  });

  $("#btn-random").addEventListener("click", async () => {
    state.cfg = await fetch("/api/random", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n: state.cfg.n }),
    }).then((r) => r.json());
    syncInputs(); draw(); scheduleCheck();
  });

  $("#btn-clear").addEventListener("click", () => {
    const { H, V } = blank(state.cfg.n);
    state.cfg.H = H; state.cfg.V = V;
    state.cfg.holes = []; state.cfg.node_holes = [];
    draw(); scheduleCheck();
  });

  $("#start-side").addEventListener("change", (e) => {
    state.cfg.start_side = e.target.value; draw(); scheduleCheck();
  });
  $("#end-side").addEventListener("change", (e) => {
    state.cfg.end_side = e.target.value; draw(); scheduleCheck();
  });

  $("#btn-build").addEventListener("click", build);
  $("#btn-gif").addEventListener("click", makeGif);

  $("#btn-export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(state.cfg, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `maze_${state.cfg.n}x${state.cfg.n}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("#btn-import").addEventListener("click", () => $("#file-import").click());
  $("#file-import").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    state.cfg = JSON.parse(await f.text());
    syncInputs(); draw(); scheduleCheck();
    e.target.value = "";
  });

  window.addEventListener("keydown", (e) => {
    if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    const map = { 1: "wall", 2: "hole", 3: "node", 4: "move", 5: "start", 6: "end" };
    if (map[e.key]) {
      document.querySelector(`[data-tool="${map[e.key]}"]`).click();
      return;
    }
    if (state.tool !== "move" || !state.sel) return;
    if (e.key === "Delete" || e.key === "Backspace") {
      const h = getHole(state.sel.kind, state.sel.idx);
      if (!h) return;
      if (state.sel.kind === "cell") state.cfg.holes.splice(state.sel.idx, 1);
      else state.cfg.node_holes.splice(state.sel.idx, 1);
      state.sel = null;
      e.preventDefault();
      draw(); scheduleCheck();
      return;
    }
    const step = e.shiftKey ? 2 : 0.5;
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!d) return;
    e.preventDefault();
    const h = getHole(state.sel.kind, state.sel.idx);
    if (!h) return;
    const [bx, by] = baseCenter(state.sel.kind, h);
    const T = total(state.cfg);
    h.dx = r1(clamp((h.dx || 0) + d[0], -bx, T - bx));
    h.dy = r1(clamp((h.dy || 0) + d[1], -by, T - by));
    draw(); scheduleCheck();
  });

  new ResizeObserver(() => draw()).observe(canvas.parentElement);
}

/* ------------------------------------------------------------ 表单 */
function buildFields() {
  const box = $("#fields");
  box.innerHTML = "";
  for (const [key, label, min, max, step] of FIELDS) {
    const l = document.createElement("label");
    l.innerHTML = `<span>${label}</span><input id="f-${key}" type="number"
      min="${min}" max="${max}" step="${step}">`;
    box.appendChild(l);
    l.querySelector("input").addEventListener("input", (e) => {
      const v = parseFloat(e.target.value);
      if (!isFinite(v)) return;
      if (key === "n") resizeGrid(Math.max(4, Math.min(12, Math.round(v))));
      else state.cfg[key] = Math.max(min, Math.min(max, v));
      draw(); scheduleCheck();
    });
  }
}

function syncInputs() {
  for (const [key] of FIELDS) {
    const el = $(`#f-${key}`);
    if (el) el.value = state.cfg[key];
  }
  $("#start-side").value = state.cfg.start_side;
  $("#end-side").value = state.cfg.end_side;
}

/* ------------------------------------------------------------ 校验 */
let checkTimer = null;
function scheduleCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(runCheck, 240);
}

async function runCheck() {
  try {
    const r = await fetch("/api/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.cfg),
    });
    state.check = await r.json();
    renderStatus();
    draw();
  } catch (err) { console.error(err); }
}

function renderStatus() {
  const ck = state.check;
  if (!ck) return;
  const ok = ck.ok;
  const rows = [
    ["最短步数", ck.steps ?? "—", ""],
    ["连通格数", `${ck.reachable}/${ck.cells}`, ck.reachable === ck.free_cells ? "good" : "warn"],
    ["球心净宽", ck.ball_path ? "通过" : "不够", ck.ball_path ? "good" : "warn"],
    ["外形", `${ck.total[0].toFixed(1)}×${ck.total[1].toFixed(1)}×${ck.total[2].toFixed(1)}`, ""],
  ];
  $("#status").innerHTML =
    `<div class="verdict ${ok ? "ok" : "bad"}">${ok ? "✓ 可以通关" : "✗ 走不通"}</div>
     <div class="rows">${rows.map(([k, v, cls]) =>
       `<div><span>${k}</span><b class="${cls}">${v}</b></div>`).join("")}</div>`;

  const w = ck.warnings || [];
  $("#warnings").innerHTML = w.map((t) => `<div class="warn">${t}</div>`).join("");
}

/* ------------------------------------------------------------ 生成 */
async function build() {
  const btn = $("#btn-build");
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span> 正在生成…`;
  $("#result").innerHTML = "";
  try {
    const r = await fetch("/api/build", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.cfg),
    });
    const d = await r.json();
    const s = d.stats;
    $("#result").innerHTML = `
      <img src="${d.png}?t=${Date.now()}" alt="3D 预览">
      <div class="meta">
        <div>三角面 <b>${s.triangles}</b></div>
        <div>体积 <b>${s.volume_cm3} cm³</b></div>
        <div>耗材 <b>≈${s.grams} g</b></div>
        <div>水密 <b>${s.watertight ? "✓" : "✗"}</b></div>
        <div>尺寸 <b>${s.bbox[0]}×${s.bbox[1]}×${s.bbox[2]}</b></div>
        <div>用时 <b>${s.seconds}s</b></div>
      </div>
      <a class="dl" href="${d.stl}" download>⬇ 下载 STL</a>`;
  } catch (e) {
    $("#result").innerHTML = `<div class="warn">生成失败：${e}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "生成 3D 模型";
  }
}

async function makeGif() {
  const btn = $("#btn-gif");
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span> 排队中…`;
  $("#result").innerHTML = `<div class="progress"><i></i></div><div class="pct">0%</div>`;
  try {
    const r = await fetch("/api/gif", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state.cfg, opts: { frames: 72, gif_px: 720 } }),
    });
    const { job } = await r.json();
    clearInterval(state.gifTimer);
    state.gifTimer = setInterval(async () => {
      const j = await fetch(`/api/job/${job}`).then((x) => x.json());
      const bar = document.querySelector(".progress > i");
      const pct = document.querySelector(".pct");
      if (bar) bar.style.width = `${j.progress || 0}%`;
      if (pct) pct.textContent = j.status === "done"
        ? `完成 · ${j.mb} MB` : `渲染中 ${Math.round(j.progress || 0)}%`;
      if (j.status === "done") {
        clearInterval(state.gifTimer);
        btn.disabled = false;
        btn.textContent = "生成环绕 GIF";
        $("#result").innerHTML = `
          <img src="${j.url}?t=${Date.now()}" alt="环绕 GIF">
          <a class="dl" href="${j.url}" download>⬇ 下载 GIF</a>`;
      }
      if (j.status === "error") {
        clearInterval(state.gifTimer);
        btn.disabled = false;
        btn.textContent = "生成环绕 GIF";
        $("#result").innerHTML = `<div class="warn">GIF 渲染失败</div>`;
      }
    }, 700);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "生成环绕 GIF";
  }
}

/* ------------------------------------------------------------ 启动 */
(async function init() {
  buildFields();
  bind();
  state.cfg = await fetch("/api/preset/classic").then((r) => r.json());
  syncInputs();
  draw();
  runCheck();
})();
