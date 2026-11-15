# -*- coding: utf-8 -*-
"""通用弹珠迷宫内核：配置 -> 几何 / 校验 / 平面图。

与 marble_maze.py 的区别：这里所有参数（格数、路宽、墙厚、孔位、起终点…）
都来自 Config，可被 Web UI 任意配置。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

import manifold3d as mf
import numpy as np
import trimesh

SIDES = ("top", "right", "bottom", "left")


# --------------------------------------------------------------------- 工具
def box(x0, y0, z0, x1, y1, z1) -> mf.Manifold:
    return mf.Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl_z(cx, cy, r, z0, z1, seg=96) -> mf.Manifold:
    return mf.Manifold.cylinder(z1 - z0, r, r, seg, center=False).translate((cx, cy, z0))


def cyl_axis(cx, cy, cz, r, length, axis, seg=96) -> mf.Manifold:
    """沿 +axis 的圆柱，从 (cx,cy,cz) 起。"""
    m = mf.Manifold.cylinder(length, r, r, seg, center=False)
    if axis == "y":
        m = m.rotate((-90, 0, 0))          # +z -> +y
    elif axis == "x":
        m = m.rotate((0, 90, 0))           # +z -> +x
    return m.translate((cx, cy, cz))


def blank_walls(n: int):
    H = [[0] * n for _ in range(n + 1)]
    V = [[0] * (n + 1) for _ in range(n)]
    for c in range(n):
        H[0][c] = H[n][c] = 1
    for r in range(n):
        V[r][0] = V[r][n] = 1
    return H, V


# --------------------------------------------------------------------- 配置
@dataclass
class Config:
    n: int = 8
    path_w: float = 18.0
    wall_t: float = 3.375
    floor_t: float = 8.0
    wall_h: float = 25.0
    ball_d: float = 14.0
    hole_d: float = 16.0
    entry_d: float = 16.0
    entry_sill: float = 4.0
    exit_w: float = 14.0

    start: list = field(default_factory=lambda: [0, 0])
    end: list = field(default_factory=lambda: [2, 0])
    start_side: str = "top"
    end_side: str = "left"

    H: list = field(default_factory=list)          # (n+1) x n
    V: list = field(default_factory=list)          # n x (n+1)
    holes: list = field(default_factory=list)      # {"r","c","d","dx","dy"}
    node_holes: list = field(default_factory=list) # {"j","i","d","dx","dy"}  j,i = 1..n-1

    # ---------------------------------------------------------- 派生
    def __post_init__(self):
        self.n = max(3, min(14, int(self.n)))
        self.normalize()

    def normalize(self):
        n = self.n
        # 墙图补齐 / 裁剪
        H = [list(row[:n]) + [0] * max(0, n - len(row)) for row in (self.H or [])][: n + 1]
        while len(H) < n + 1:
            H.append([0] * n)
        V = [list(row[: n + 1]) + [0] * max(0, n + 1 - len(row)) for row in (self.V or [])][:n]
        while len(V) < n:
            V.append([0] * (n + 1))
        H, V = [[int(bool(v)) for v in row] for row in H], [[int(bool(v)) for v in row] for row in V]
        for c in range(n):
            H[0][c] = H[n][c] = 1
        for r in range(n):
            V[r][0] = V[r][n] = 1
        self.H, self.V = H, V

        self.start = [int(max(0, min(n - 1, self.start[0]))), int(max(0, min(n - 1, self.start[1])))]
        self.end = [int(max(0, min(n - 1, self.end[0]))), int(max(0, min(n - 1, self.end[1])))]
        if self.start_side not in SIDES:
            self.start_side = "top"
        if self.end_side not in SIDES:
            self.end_side = "left"

        clean = []
        for h in self.holes:
            r, c = int(h["r"]), int(h["c"])
            if 0 <= r < n and 0 <= c < n:
                clean.append({"r": r, "c": c, "d": float(h.get("d", self.hole_d)),
                              "dx": float(h.get("dx", 0.0)), "dy": float(h.get("dy", 0.0))})
        self.holes = clean
        nclean = []
        for h in self.node_holes:
            j, i = int(h["j"]), int(h["i"])
            if 1 <= j <= n - 1 and 1 <= i <= n - 1:
                nclean.append({"j": j, "i": i, "d": float(h.get("d", 18.0)),
                               "dx": float(h.get("dx", 0.0)), "dy": float(h.get("dy", 0.0))})
        self.node_holes = nclean

    # ---------------------------------------------------------- 尺寸
    @property
    def pitch(self) -> float:
        return self.path_w + self.wall_t

    @property
    def total(self) -> float:
        return self.n * self.path_w + (self.n + 1) * self.wall_t

    @property
    def height(self) -> float:
        return self.floor_t + self.wall_h

    def cell_center(self, r: int, c: int) -> tuple[float, float]:
        return (c * self.pitch + self.wall_t + self.path_w / 2,
                r * self.pitch + self.wall_t + self.path_w / 2)

    def node_center(self, j: int, i: int) -> tuple[float, float]:
        return (i * self.pitch, j * self.pitch)

    def hole_xy(self, h) -> tuple[float, float]:
        cx, cy = self.cell_center(h["r"], h["c"])
        return cx + h.get("dx", 0.0), cy + h.get("dy", 0.0)

    def node_hole_xy(self, h) -> tuple[float, float]:
        cx, cy = self.node_center(h["j"], h["i"])
        return cx + h.get("dx", 0.0), cy + h.get("dy", 0.0)

    def all_holes(self):
        """[(cx, cy, r, kind, index)]"""
        out = []
        for k, h in enumerate(self.holes, 1):
            cx, cy = self.hole_xy(h)
            out.append((cx, cy, h["d"] / 2, "cell", k))
        for k, h in enumerate(self.node_holes, len(self.holes) + 1):
            cx, cy = self.node_hole_xy(h)
            out.append((cx, cy, h["d"] / 2, "node", k))
        return out

    # ---------------------------------------------------------- 几何
    def footprint_rects(self):
        n, p, t = self.n, self.pitch, self.wall_t
        rects = []
        for j in range(n + 1):
            for c in range(n):
                if self.H[j][c]:
                    rects.append((c * p, j * p, p + t, t))
        for r in range(n):
            for i in range(n + 1):
                if self.V[r][i]:
                    rects.append((i * p, r * p, t, p + t))
        return rects

    def opening(self, cell, side, w, z0, rounded, depth=1.0):
        """边界墙上的开口（入口圆孔 / 出口方孔）。"""
        n, t, T = self.n, self.wall_t, self.total
        cx, cy = self.cell_center(*cell)
        if side in ("top", "bottom"):
            y0, y1 = (-depth, t + depth) if side == "top" else (T - t - depth, T + depth)
            zc = z0 + w / 2
            if rounded:
                return cyl_axis(cx, y0, zc, w / 2, y1 - y0, "y")
            return box(cx - w / 2, y0, z0, cx + w / 2, y1, z0 + w)
        x0, x1 = (-depth, t + depth) if side == "left" else (T - t - depth, T + depth)
        zc = z0 + w / 2
        if rounded:
            return cyl_axis(x0, cy, zc, w / 2, x1 - x0, "x")
        return box(x0, cy - w / 2, z0, x1, cy + w / 2, z0 + w)

    def build(self) -> mf.Manifold:
        base = box(0, 0, 0, self.total, self.total, self.floor_t)
        cs = mf.CrossSection.batch_boolean(
            [mf.CrossSection.square((w, h), center=False).translate((x, y))
             for x, y, w, h in self.footprint_rects()], mf.OpType.Add)
        solid = base + cs.extrude(self.wall_h).translate((0, 0, self.floor_t))

        for cx, cy, r, _, _ in self.all_holes():
            solid = solid - cyl_z(cx, cy, r, -1.0, self.floor_t + 1.0)

        z0 = self.floor_t + self.entry_sill
        solid = solid - self.opening(self.start, self.start_side, self.entry_d, z0, rounded=True)
        solid = solid - self.opening(self.end, self.end_side, self.exit_w, self.floor_t, rounded=False)
        return solid

    def to_trimesh(self) -> trimesh.Trimesh:
        me = self.build().to_mesh()
        v = np.asarray(me.vert_properties)[:, :3]
        f = np.asarray(me.tri_verts)
        return trimesh.Trimesh(vertices=v, faces=f, process=True)

    # ---------------------------------------------------------- 校验
    def hole_cells(self):
        """孔实际所在的格子：按孔心归格，拖走后旧格子自动放行。"""
        n, p = self.n, self.pitch
        out = set()
        for h in self.holes:
            cx, cy = self.hole_xy(h)
            c = min(n - 1, max(0, int(cx // p)))
            r = min(n - 1, max(0, int(cy // p)))
            out.add((r, c))
        return out

    def nbrs(self, r, c):
        n = self.n
        if r > 0 and not self.H[r][c]:
            yield r - 1, c
        if r < n - 1 and not self.H[r + 1][c]:
            yield r + 1, c
        if c > 0 and not self.V[r][c]:
            yield r, c - 1
        if c < n - 1 and not self.V[r][c + 1]:
            yield r, c + 1

    def bfs(self):
        """避开格心孔的格间最短路。返回 (path, all_reachable)"""
        from collections import deque
        blocked = self.hole_cells()
        s, t = tuple(self.start), tuple(self.end)
        prev = {s: None}
        dq = deque([s])
        while dq:
            cur = dq.popleft()
            if cur == t:
                break
            for nb in self.nbrs(*cur):
                if nb in prev or nb in blocked:
                    continue
                prev[nb] = cur
                dq.append(nb)
        # 全连通统计
        seen = {s}
        dq = deque([s])
        while dq:
            cur = dq.popleft()
            for nb in self.nbrs(*cur):
                if nb not in seen and nb not in blocked:
                    seen.add(nb)
                    dq.append(nb)
        if t not in prev:
            return None, seen
        path, cur = [], t
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        return path[::-1], seen

    def raster(self, step: float = 0.5):
        T = self.total
        m = int(np.ceil(T / step)) + 1
        xs = np.arange(m) * step
        X, Y = np.meshgrid(xs, xs)
        wall = np.zeros((m, m), bool)
        for (x0, y0, w, h) in self.footprint_rects():
            i0 = max(0, int(np.floor(x0 / step)) - 1)
            i1 = min(m, int(np.ceil((x0 + w) / step)) + 2)
            j0 = max(0, int(np.floor(y0 / step)) - 1)
            j1 = min(m, int(np.ceil((y0 + h) / step)) + 2)
            sub_x, sub_y = X[j0:j1, i0:i1], Y[j0:j1, i0:i1]
            wall[j0:j1, i0:i1] |= ((sub_x >= x0) & (sub_x <= x0 + w) &
                                   (sub_y >= y0) & (sub_y <= y0 + h))
        hole = np.zeros((m, m), bool)
        for cx, cy, r, _, _ in self.all_holes():
            hole |= ((X - cx) ** 2 + (Y - cy) ** 2) <= r * r
        return X, Y, wall, hole

    def check_geometric(self, step: float = 0.5):
        """球心可达性：球心离墙 >= 半径，且球心不落在孔上。"""
        from scipy import ndimage
        X, Y, wall, hole = self.raster(step)
        dist = ndimage.distance_transform_edt(~wall, sampling=step)
        free = (dist >= self.ball_d / 2) & (~hole)
        lab, _ = ndimage.label(free)
        h = step / 2

        def at(pt):
            i = int(round(pt[0] / step))
            j = int(round(pt[1] / step))
            return lab[j, i] if 0 <= j < lab.shape[0] and 0 <= i < lab.shape[1] else 0

        s = at(self.cell_center(*self.start))
        t = at(self.cell_center(*self.end))
        ok = bool(s != 0 and s == t)
        return ok, {"start_label": int(s), "end_label": int(t),
                    "free_area_cm2": float(free.sum() * step * step / 100.0)}

    def diagnose(self) -> dict:
        path, seen = self.bfs()
        blocked = self.hole_cells()
        free_cells = self.n * self.n - len(blocked)
        # 孔干涉
        warnings, holes = [], self.all_holes()
        rects = self.footprint_rects()

        def dist_to_walls(cx, cy):
            best = 1e9
            for (x0, y0, w, h) in rects:
                dx = max(x0 - cx, 0.0, cx - (x0 + w))
                dy = max(y0 - cy, 0.0, cy - (y0 + h))
                best = min(best, (dx * dx + dy * dy) ** 0.5)
            return best

        for cx, cy, r, kind, k in holes:
            d = dist_to_walls(cx, cy)
            if d < r - 0.05:
                warnings.append(f"孔 {k} 切进了墙体 {r - d:.1f} mm")
        for a in range(len(holes)):
            for b in range(a + 1, len(holes)):
                gap = np.hypot(holes[a][0] - holes[b][0], holes[a][1] - holes[b][1]) - holes[a][2] - holes[b][2]
                if gap < 1.0:
                    warnings.append(f"孔 {holes[a][4]} 与孔 {holes[b][4]} 粘连（间隙 {max(gap, 0):.1f} mm）")
        if len(seen) < free_cells:
            warnings.append(f"有 {free_cells - len(seen)} 格被墙封死，走不到")
        if tuple(self.start) in blocked:
            warnings.append("起点格上有落球孔")
        if tuple(self.end) in blocked:
            warnings.append("终点格上有落球孔")
        if self.exit_w < self.ball_d:
            warnings.append(f"出口 {self.exit_w:g} mm 小于球径 {self.ball_d:g} mm，球出不去")
        if self.entry_sill + self.entry_d > self.wall_h:
            warnings.append("入口孔顶高超过墙高，孔会穿出墙顶")
        if self.entry_d < self.ball_d:
            warnings.append("入口孔径小于球径")

        geo_ok, geo = self.check_geometric()
        if path and not geo_ok:
            warnings.append("格心路径存在，但球的实际净宽不够（贴墙也过不去）")

        return {
            "ok": bool(path) and geo_ok,
            "steps": len(path) - 1 if path else None,
            "path": path,
            "reachable": len(seen),
            "free_cells": free_cells,
            "cells": self.n * self.n,
            "ball_path": geo_ok,
            "geo": geo,
            "warnings": warnings,
            "total": [round(self.total, 3), round(self.total, 3), round(self.height, 3)],
        }

    # ---------------------------------------------------------- 序列化
    def to_dict(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        d["pitch"] = self.pitch
        d["height"] = self.height
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        keys = {f for f in cls.__dataclass_fields__}
        kw = {k: v for k, v in (d or {}).items() if k in keys}
        for k in ("n",):
            if k in kw:
                kw[k] = int(kw[k])
        return cls(**kw)


# --------------------------------------------------------------------- 预设
def classic() -> Config:
    H = [[1, 1, 1, 1, 1, 1, 1, 1],
         [0, 0, 1, 0, 0, 0, 0, 0],
         [1, 1, 0, 0, 0, 0, 0, 0],
         [0, 0, 1, 0, 1, 0, 0, 0],
         [0, 0, 0, 1, 1, 0, 0, 0],
         [0, 1, 1, 1, 1, 1, 0, 0],
         [1, 0, 0, 0, 1, 0, 0, 0],
         [1, 0, 1, 1, 1, 0, 1, 0],
         [1, 1, 1, 1, 1, 1, 1, 1]]
    V = [[1, 1, 0, 0, 0, 1, 0, 1, 1],
         [1, 0, 0, 0, 0, 0, 0, 1, 1],
         [1, 1, 0, 0, 1, 0, 1, 1, 1],
         [1, 1, 0, 1, 0, 0, 0, 0, 1],
         [1, 1, 0, 0, 0, 0, 1, 1, 1],
         [1, 0, 0, 0, 0, 0, 0, 0, 1],
         [1, 0, 0, 1, 0, 0, 0, 1, 1],
         [1, 0, 0, 0, 0, 0, 0, 0, 1]]
    return Config(
        n=8, H=H, V=V,
        holes=[{"r": 1, "c": 4, "d": 16},
               {"r": 2, "c": 3, "d": 16, "dx": -8.6, "dy": -10.6},
               {"r": 1, "c": 6, "d": 18, "dx": -3.5, "dy": -3.5},
               {"r": 5, "c": 6, "d": 16}],
        node_holes=[{"j": 4, "i": 2, "d": 18},
                    {"j": 6, "i": 2, "d": 18},
                    {"j": 6, "i": 6, "d": 18, "dx": -2.8, "dy": 5.8}],
        start=[0, 0], end=[2, 0], start_side="top", end_side="left")


def random_maze(n: int = 8, seed: int | None = None) -> Config:
    """递归回溯生成完美迷宫 + 少量回路 + 保证有解的落球孔。"""
    rng = np.random.default_rng(seed)
    H = [[1] * n for _ in range(n + 1)]
    V = [[1] * (n + 1) for _ in range(n)]
    seen = np.zeros((n, n), bool)
    stack = [(0, 0)]
    seen[0, 0] = True
    while stack:
        r, c = stack[-1]
        opts = [(r - 1, c, "H", r, c), (r + 1, c, "H", r + 1, c),
                (r, c - 1, "V", r, c), (r, c + 1, "V", r, c + 1)]
        opts = [o for o in opts if 0 <= o[0] < n and 0 <= o[1] < n and not seen[o[0], o[1]]]
        if not opts:
            stack.pop()
            continue
        nr, nc, kind, a, b = opts[int(rng.integers(len(opts)))]
        if kind == "H":
            H[a][b] = 0
        else:
            V[a][b] = 0
        seen[nr, nc] = True
        stack.append((nr, nc))

    # 打掉少量内墙形成回路
    for _ in range(max(1, n * n // 8)):
        if rng.random() < 0.5:
            r = int(rng.integers(1, n - 1))
            c = int(rng.integers(0, n))
            H[r][c] = 0
        else:
            r = int(rng.integers(0, n))
            c = int(rng.integers(1, n - 1))
            V[r][c] = 0

    cfg = Config(n=n, H=H, V=V, start=[0, 0], end=[n - 1, 0],
                 start_side="top", end_side="left")
    # 逐个加孔，保证仍可解
    cells = [(r, c) for r in range(n) for c in range(n)]
    rng.shuffle(cells)
    want = max(3, int(n * n * 0.10))
    for (r, c) in cells:
        if len(cfg.holes) >= want:
            break
        if (r, c) in (tuple(cfg.start), tuple(cfg.end)):
            continue
        trial = Config.from_dict({**cfg.to_dict(), "holes": cfg.holes + [{"r": r, "c": c, "d": 16}]})
        if trial.bfs()[0] is not None:
            cfg = trial
    return cfg
