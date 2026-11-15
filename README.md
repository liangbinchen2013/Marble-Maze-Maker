# 弹珠迷宫 DIY

[MakerWorld模型](https://makerworld.com.cn/zh/models/3262461-dan-zhu-mi-gong#profileId-3854015)

浏览器里画墙、挖孔、**自由拖动**，实时校验能不能通关，一键导出 **STL** 和 **360° 环绕 GIF**。

## 启动

双击 **`启动迷宫编辑器.bat`** → 浏览器自动打开 <http://127.0.0.1:8000>

或者手动：

```powershell
cd maze_studio
python server.py --port 8000 --open
```

首次使用需要装依赖：

```powershell
pip install flask trimesh manifold3d numpy scipy pillow vtk
```

## 目录

```
maze_studio/              应用本体
├── server.py             Flask 服务（校验 / 生成 STL / 渲染 GIF）
├── maze_core.py          内核：配置 → 实体、BFS、球心泛洪
├── maze_render3d.py      VTK 离屏渲染
├── ui/                   前端（原生 JS + Canvas，无构建）
├── outputs/              生成物
└── README.md             详细说明
启动迷宫编辑器.bat          启动器
```

## 旧版

最初那个 8×8 迷宫（手绘草图、STL、平面图、剖面图、环绕 GIF、生成脚本）已归档到 **`D:\3D\`**。

在编辑器顶栏点 **「经典 8×8」** 就能一键载入那套配置，继续改或直接导出。
