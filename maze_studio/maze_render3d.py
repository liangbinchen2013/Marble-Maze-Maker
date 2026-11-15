# -*- coding: utf-8 -*-
"""VTK 离屏渲染：3D 预览图 + 360° 环绕 GIF。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
import vtk
from PIL import Image
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy


# ------------------------------------------------------------------ 基础
def hex_rgb(s: str) -> tuple[float, float, float]:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _polydata(v, f):
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.ascontiguousarray(v, dtype=np.float64), deep=True))
    cells = vtk.vtkCellArray()
    for tri in f:
        cells.InsertNextCell(3)
        for idx in tri:
            cells.InsertCellPoint(int(idx))
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    n = vtk.vtkPolyDataNormals()
    n.SetInputData(pd)
    n.ComputePointNormalsOff()
    n.ComputeCellNormalsOn()
    n.SplittingOff()
    n.Update()
    return n.GetOutput()


def _sphere(center, r, color):
    src = vtk.vtkSphereSource()
    src.SetCenter(*center)
    src.SetRadius(r)
    src.SetThetaResolution(64)
    src.SetPhiResolution(32)
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(src.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(m)
    p = a.GetProperty()
    p.SetColor(*color)
    p.SetAmbient(0.35)
    p.SetDiffuse(0.65)
    p.SetSpecular(0.45)
    p.SetSpecularPower(40)
    return a


def build_scene(mesh: trimesh.Trimesh, balls, bg, color, edge_color):
    pd = _polydata(mesh.vertices, mesh.faces)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    p = actor.GetProperty()
    p.SetColor(*color)
    p.SetAmbient(0.45)
    p.SetDiffuse(0.62)
    p.SetSpecular(0.18)
    p.SetSpecularPower(24)
    p.SetInterpolationToPhong()

    ren = vtk.vtkRenderer()
    ren.SetBackground(*bg)
    ren.AddActor(actor)

    e = vtk.vtkFeatureEdges()
    e.SetInputData(pd)
    e.BoundaryEdgesOff()
    e.NonManifoldEdgesOff()
    e.ManifoldEdgesOff()
    e.FeatureEdgesOn()
    e.SetFeatureAngle(35)
    em = vtk.vtkPolyDataMapper()
    em.SetInputConnection(e.GetOutputPort())
    em.ScalarVisibilityOff()
    ea = vtk.vtkActor()
    ea.SetMapper(em)
    ea.GetProperty().SetColor(*edge_color)
    ea.GetProperty().SetLineWidth(1.1)
    ren.AddActor(ea)

    for c, r, col in balls:
        ren.AddActor(_sphere(c, r, col))

    lo, hi = mesh.bounds.reshape(2, 3)
    centre = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) * 1.6

    for pos, inten in [((0.8, -1, 1.7), 0.80), ((-1.3, -0.5, 0.7), 0.40), ((0.1, 1.5, 0.6), 0.25)]:
        lt = vtk.vtkLight()
        lt.SetPosition(centre[0] + pos[0] * radius,
                       centre[1] + pos[1] * radius,
                       centre[2] + pos[2] * radius)
        lt.SetFocalPoint(*centre)
        lt.SetIntensity(inten)
        ren.AddLight(lt)
    ren.LightFollowCameraOn()

    return ren, centre, radius


def grab(rw) -> np.ndarray:
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    img = w2i.GetOutput()
    w, h, _ = img.GetDimensions()
    arr = vtk_to_numpy(img.GetPointData().GetScalars())
    return arr.reshape(h, w, 3)[::-1].copy()


def _setup(mesh, balls, w, h, elev, color, edge, bg=(1.0, 1.0, 1.0)):
    ren, centre, radius = build_scene(mesh, balls, bg, hex_rgb(color), hex_rgb(edge))
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(w, h)
    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(*centre)
    cam.SetViewUp(0, 0, 1)
    el = np.radians(elev)

    def place(az_deg, dist):
        az = np.radians(az_deg)
        cam.SetPosition(centre[0] + dist * np.cos(el) * np.cos(az),
                        centre[1] + dist * np.cos(el) * np.sin(az),
                        centre[2] + dist * np.sin(el))
        ren.ResetCameraClippingRange()

    place(-45, radius)
    ren.ResetCamera()
    ren.ResetCameraClippingRange()
    d0, va0 = cam.GetDistance(), cam.GetViewAngle()
    dist = d0 * 2.5
    cam.SetViewAngle(float(np.degrees(2 * np.arctan(np.tan(np.radians(va0 / 2)) / 2.5))))
    return ren, rw, cam, centre, dist, place


def _framing(ren, rw, cam, place, dist, fill):
    """自动居中 + 收敛填充率（透视下近角会撑出画面，必须实测标定）。"""
    def snap():
        place(-45, dist)
        rw.Render()
        a = grab(rw)
        m = a.min(axis=2) < 250
        ys, xs = np.where(m)
        return a, xs, ys

    def center_image():
        a, xs, ys = snap()
        H, W = a.shape[:2]
        wc = cam.GetWindowCenter()
        for axis in (0, 1):
            c0 = (xs.min() + xs.max()) / 2 if axis == 0 else (ys.min() + ys.max()) / 2
            probe = 0.05
            cam.SetWindowCenter(wc[0] + probe, wc[1]) if axis == 0 else \
                cam.SetWindowCenter(wc[0], wc[1] + probe)
            a2, xs2, ys2 = snap()
            c1 = (xs2.min() + xs2.max()) / 2 if axis == 0 else (ys2.min() + ys2.max()) / 2
            k = (c1 - c0) / probe
            mid = (W if axis == 0 else H) / 2
            if abs(k) > 1e-6:
                off = probe + (mid - c1) / k
                cam.SetWindowCenter(wc[0] + off, wc[1]) if axis == 0 else \
                    cam.SetWindowCenter(wc[0], wc[1] + off)
            wc = cam.GetWindowCenter()

    for _ in range(3):
        center_image()
        a, xs, ys = snap()
        H, W = a.shape[:2]
        f = max((xs.max() - xs.min()) / W, (ys.max() - ys.min()) / H)
        if abs(f - fill) < 0.01:
            break
        cam.Zoom(fill / f)


# ------------------------------------------------------------------ 对外
def still(mesh, balls, out: Path, w=1200, h=900, elev=34, color="#F0872A",
          edge="#5A3410", fill=0.86, az=-45):
    ren, rw, cam, centre, dist, place = _setup(mesh, balls, w, h, elev, color, edge)
    _framing(ren, rw, cam, place, dist, fill)
    place(az, dist)
    rw.Render()
    Image.fromarray(grab(rw)).save(out)
    return out


def orbit(mesh, balls, out: Path, frames=72, w=960, h=720, elev=34, color="#F0872A",
          edge="#5A3410", fps=20, gif_px=720, colors=128, fill=0.94, progress=None):
    ren, rw, cam, centre, dist, place = _setup(mesh, balls, w, h, elev, color, edge)
    _framing(ren, rw, cam, place, dist, fill)

    imgs = []
    for k in range(frames):
        place(-90 + 360.0 * k / frames, dist)
        rw.Render()
        imgs.append(grab(rw))
        if progress:
            progress((k + 1) / frames)

    scale = gif_px / w
    gw, gh = int(w * scale), int(h * scale)
    rgb = [Image.fromarray(f).resize((gw, gh), Image.LANCZOS) for f in imgs]
    sample = [0, len(rgb) // 4, len(rgb) // 2, 3 * len(rgb) // 4]
    montage = Image.new("RGB", (gw, gh * len(sample)), "white")
    for i, k in enumerate(sample):
        montage.paste(rgb[k], (0, i * gh))
    pal = montage.quantize(colors=colors, method=Image.MEDIANCUT)
    gif = [im.quantize(palette=pal, dither=Image.NONE) for im in rgb]
    gif[0].save(out, save_all=True, append_images=gif[1:],
                duration=int(round(1000 / fps)), loop=0, optimize=True, disposal=2)
    return out
