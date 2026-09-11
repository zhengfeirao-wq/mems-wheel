# outline

触觉夹爪的**二维采样点**与**三维结构模型**。

| 子目录 | 内容 |
|---|---|
| [`2d_sampling_points/`](2d_sampling_points/) | 12 点板 / 32 点板的传感器平面坐标：常量模块、原始 CSV、坐标图（PNG + Markdown）、绘图脚本 |
| [`3d_structure/`](3d_structure/) | 夹爪三维结构：STEP 结构件与装配体、Blender 模型与渲染图、可编辑预览（HTML/three.js）、几何校验数据 |

---

## 2d_sampling_points

传感器在平面上的采样点坐标，**12 点板与 32 点板各一套**。

| 文件 | 说明 |
|---|---|
| `sensor_coords.py` | **坐标常量模块**，上位机与可视化直接 `import`，无需解析 CSV |
| `coord_Big_raw.csv` | 32 点板原始坐标（`sensor_Number, X_coord, Y_coord`） |
| `coord_Small_raw.csv` | 12 点板原始坐标 |
| `传感器坐标图.md` | 坐标图文档：嵌入 PNG + 纯文本 ASCII 坐标图 + 逐行坐标表 + 结构分析 |
| `coord_plot_all.png` | 总览：两板单图 + 同坐标系叠加 |
| `coord_plot_big32.png` / `coord_plot_small12.png` | 单板大图 |
| `make_sensor_coords.py` | 生成器：CSV → `sensor_coords.py`（数值逐字照抄） |
| `plot_coords.py` | 绘图：常量 → PNG，并校验等比例与说明框不遮挡数据点 |
| `make_coord_md.py` | 生成器：常量 → `传感器坐标图.md` |

### 坐标约定

* **每块板的左下角 = (0, 0)**，Y 轴向上。平移量 = 该板自己的 `(x_min, y_min)`，**只平移，不缩放、不旋转、不镜像**。
* 两块板用的是同一套规则，因此对齐到同一原点后可以直接比较尺寸与节距。
* 原始绝对坐标（与 CSV 逐字一致）保留在 `sensor_coords.py` 的 `*_COORDS` / `*_XY` 里。

| 板 | 点数 | 平移量 | 原点化尺寸 宽 × 高 |
|---|---:|---|---|
| Big 32 点 | 32 | (127.531, 55.6552) | 42.4614 × 27.5869 |
| Small 12 点 | 12 | (105.8507, 71.1159) | 11.3550 × 29.9387 |

### 用法

```python
from sensor_coords import xy_rel_for, coords_rel_for, normalized_xy, size_for

xy_rel_for(17, 32)    # -> (0.0, 0.0)        Big 板左下角
xy_rel_for(23, 32)    # -> (42.4614, 8.975)  最远点
coords_rel_for(12)    # -> Small 板整张表
normalized_xy(32)     # -> {通道号: (u, v)}，u = X/宽, v = Y/高
normalized_xy(32, y_up=False)   # v=0 在上，屏幕坐标直接乘控件高度即可
```

重新生成（Python 3.10+，需要 matplotlib）：

```powershell
python make_sensor_coords.py     # CSV  ->  sensor_coords.py
python plot_coords.py            # 常量 ->  PNG（左下角 = (0,0)）
python plot_coords.py --raw      # 常量 ->  PNG（原始绝对坐标）
python plot_coords.py --flip     # 常量 ->  PNG（Y 轴向下）
python make_coord_md.py          # 常量 ->  传感器坐标图.md
python sensor_coords.py          # 常量模块自检
```

`plot_coords.py` 会逐面板校验**等比例**（`ratio` 必须为 `1.0000`）与**说明框是否遮挡数据点**（必须为 0 个）。

坐标数据源自 [`3d_structure/editable_gripper_preview/coordinates/`](3d_structure/editable_gripper_preview/coordinates/)，两处 `coord_*_raw.csv` 内容一致。

---

## 3d_structure

夹爪三维结构模型与可编辑预览。

| 项 | 说明 |
|---|---|
| `onebody-12-jiegoujian.STEP` / `onebody-32-jiegoujian.STEP` | 12 点 / 32 点结构件 STEP |
| `editable_gripper_preview/cad/12`、`cad/32` | 分件 STEP：结构本体、硅胶帽、盖板、连接器、PCB 示意，含装配体与爆炸图 |
| `editable_gripper_preview/blender/` | Blender 源文件（`.blend`）、`.glb` 与渲染 PNG |
| `editable_gripper_preview/gripper-preview.html` | 可交互三维预览（three.js，单文件、离线可用） |
| `editable_gripper_preview/mesh-data.json`、`geometry-validation.json` | 网格数据与几何校验结果 |
| `editable_gripper_preview/build_models.py`、`build_preview.py`、`verify_cad.py` | 建模与校验脚本 |
| `自适应通用夹爪传感器说明书.pdf` | 传感器说明书 |
| `baseline-manifest.json`、`README.md` | 基线清单与说明 |

### 打开预览

直接双击 `editable_gripper_preview/gripper-preview.html`（或拖进浏览器）即可，依赖已内置于 `vendor/`。

### 重新构建

```powershell
cd editable_gripper_preview
pip install -r requirements-cad.txt
python build_models.py
python build_preview.py
```

```powershell
python verify_baseline.py          # 校验基线清单
python editable_gripper_preview/verify_cad.py
```

---

## 备注

* 本目录按仓库 `.gitignore` 的规则**强制加入**了 `*.csv` 与 `__pycache__/`：前者是坐标数据源（必须入库），后者是 Python 编译缓存（如需清理见下）。
* 清理编译缓存：

  ```powershell
  git rm -r --cached outline/3d_structure/__pycache__ outline/3d_structure/**/__pycache__
  ```
