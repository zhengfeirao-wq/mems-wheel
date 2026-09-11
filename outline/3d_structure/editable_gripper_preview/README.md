# 触觉夹爪 · 尖端房顶方向修正版

当前版本为 `2026-09-08-csv-relative-layout`，包含 12 / 32 通道两个型号。两种型号的 HTML 初始视角和 Blender 保存视角均为房顶朝上；四根柔性导线按伸直状态展示。封装尖端定义为房顶（原始 CAD +Y）。传感器 XY 相对位置以 coordinates/ 下两份原始 CSV 为准，不以序号决定位置。32 通道按 Y 从大到小为 1 / 7 / 6 / 6 / 6 / 6，12 通道为 3 / 3 / 2 / 2 / 2；排间距与横向错位均保留。封装胶层安装端保留随形弧面，源坐标 Y=21.3 mm 到末端的外接触面保持同一平面；当前外表面 Z=0.2 mm。末端背面按原结构斜边贴合，局部胶厚随之变化。

## 直接使用

| 用途 | 文件 |
| --- | --- |
| 离线 HTML 爆炸图 | `gripper-preview.html` |
| 爆炸图静态图片 | `preview-12-exploded.png`、`preview-32-exploded.png` |
| Blender 原生文件 | `blender/gripper-12.blend`、`blender/gripper-32.blend` |
| 通用三维网格 | `blender/gripper-12.glb`、`blender/gripper-32.glb`，保存装配状态 |
| SolidWorks / CAD 总装 STEP | `cad/12/gripper-12-assembled.step`、`cad/32/gripper-32-assembled.step` |
| CAD 爆炸状态 STEP | 各型号目录内的 `gripper-*-exploded.step` |
| 单独结构件、胶层等 | 各型号目录内的 `Structural_body.step`、`Source_cover.step`、`Silicone_cap.step`、`PCB_illustrative.step`、`Connector_illustrative.step` |
| 其他项目调用入口 | [interface/README.md](interface/README.md) 与 [manifest.json](interface/manifest.json) |

Blender 文件中的 `Gripper_12` / `Gripper_32` 为父对象，其自定义属性 `explode` 范围为 0～1，默认 0.8。0 为装配状态，1 为完全展开。每个零件都是可单独操作的对象，保留名称、材料、分类与原 CAD 坐标关系。

## 模型依据

1. 原始两份 STEP 各含两个结构实体；主体和第二结构实体直接复用源几何。第二实体的实物名称尚未确认。
2. 黄色胶层是新增设计；名义厚度 2.2 mm、边缘内收 0.25 mm、上端起点 Y=1.3 mm 为当前参数，未做实物测量。内表面裁切贴合主体，属于变厚度封装。
3. 硅胶按贴附/粘接关系表达，本模型不另建胶水层或胶缝。
4. 32 通道按 CSV 分为 1+7+6+6+6+6，12 通道为 3+3+2+2+2；传感器中心的 XY 相对位置来自 CSV。CSV 未给单位与安装基准：当前统一按 1 坐标单位=1 mm，X 居中、最大 Y 平移至 CAD Y=33.5 mm，无旋转、镜像、分别缩放或吸附。Z 随结构曲面推定，PCB 支撑和器件尺寸为示意。PCB 厚度、器件封装和线缆尺寸尚未实物验证。
5. 爆炸方向用于展示层次，不代表真实拆卸路径；电子组件未做完整制造及装配干涉校核。
6. STEP 保留具名实体/组件，不包含原生 SolidWorks 草图特征历史。Blender / GLB 是网格，精确 CAD 曲面操作应使用 STEP。

## 源文件与重新生成

原始 STEP 和说明书保留在上一级目录，PCB 原始参考图为 `reference-pcb.png`。

- `parameters.json` / `build_models.py`：当前 CAD 生成参数和建模源代码。
- `preview.template.html` / `build_preview.py`：HTML 源模板与生成器。
- `mesh-data.json`：当前 CAD 的显示网格，供 HTML 和 Blender 共用。
- `vendor/`：离线 Three.js 与许可文件。

只更新页面时运行 `python build_preview.py`，它读取已确认的网格，不重画模型。修改模型参数后使用 Python 3.12 与 `requirements-cad.txt` 中的 CadQuery 依赖运行 `python build_models.py`，再按接口文档重建 Blender / GLB 并验证。不要手工修改 STEP 或生成的 HTML。

## 已验证与未验证

- 点位：验证实际 CAD 器件中心及导出网格与 CSV 对应，核对全部 66 / 496 对 XY 距离；序号只用于追溯数据来源。
- CAD：两种胶层均为单个有效实体，与主体重叠体积为 0；下部外表面为 CAD `PLANE`，31 截面检查误差约 1×10⁻⁷ mm。6 个胶层/装配/爆炸 STEP 已重新导入检查。
- Blender 5.2.1 LTS：两种 `.blend` 保存后重开、GLB 导出后回读、零件数量及名称、材料、坐标、爆炸位移和米/毫米场景均通过检查。导入函数保留已有场景对象。
- HTML：型号切换、爆炸程度、显隐、透明度、视角、PNG 导出、窄屏和调用接口已检查，无页面脚本异常。
- SolidWorks：已提供官方 STEP API 对应的 PowerShell / VBA 调用入口，路径解析已验证；本机未安装 SolidWorks，尚未完成 SolidWorks 实机运行或原生 `.SLDPRT` / `.SLDASM` 保存验证。
- 本机临时 CadQuery 环境有既存的退出清理异常；CAD 文件已另外重读确认有效。重建 CAD 时建议使用独立依赖环境。

CAD 检查记录见 `geometry-validation.json`、`step-roundtrip-validation.json`；接口和 Blender 检查记录见 `interface/*-validation.json`。这些检查不替代实物测量或制造公差验收。

点位源文件在 `coordinates/`，生成入口为 `sensor_layout.py`；`coordinate-layout.svg` 为无编号等比例点位图。`parameters.json` 中的坐标比例与整体 Y 定位是显式展示假设。
