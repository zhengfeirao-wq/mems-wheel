# 触觉夹爪模型 · 当前唯一版本

保留版本：**2026-09-08，房顶朝上、柔性导线伸直修正版**。PCB 与传感器已按两份 CSV 的实际 XY 相对位置重建，12 通道为 3/3/2/2/2 五排；胶层接触平面延伸至尖端的设计保留。12 通道和 32 通道是同一版本的两个型号，初始展示均为房顶朝上，导线按伸直状态表示。

- [HTML 爆炸图](editable_gripper_preview/gripper-preview.html)：离线打开，默认 32 通道、80% 爆炸程度，可切换型号。
- [Blender / SolidWorks / Python 调用说明](editable_gripper_preview/interface/README.md)：其他建模项目从这里接入。
- [机器可读接口清单](editable_gripper_preview/interface/manifest.json)：零件 ID、相对路径、单位、坐标、爆炸位移及原始文件校验值。
- [模型说明](editable_gripper_preview/README.md)：文件用途、模型依据与验证范围。

## 原始资料

`onebody-12-jiegoujian.STEP`、`onebody-32-jiegoujian.STEP` 和 `自适应通用夹爪传感器说明书.pdf` 保存在本目录；PCB 原始参考图保存在 `editable_gripper_preview/reference-pcb.png`。

搬迁或提供给其他项目时，复制整个 **（7）3D建模** 目录，保留相对路径。HTML 已内嵌模型，可以单独复制；重新建模和完整接口调用应使用整个目录。

目录只保留当前模型、原始资料、当前格式导出、必要的生成代码与接口验证文件。旧版备份、旧压缩包、修改前后对比图和临时检查产物已移入 Windows 回收站。

## 已确认的起始基准

当前文件作为后续项目的起始材料。`baseline-manifest.json` 记录文件 SHA-256；运行 `python verify_baseline.py` 可检查是否被改动。后续新设计应另存版本，不覆盖本基准。基准校验保证文件一致性；原说明中的单位、绝对安装基准和硬件接线待核实项仍适用。
