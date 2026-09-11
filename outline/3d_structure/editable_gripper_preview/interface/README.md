# Blender / SolidWorks / Python 调用接口

唯一模型版本：`2026-09-08-csv-relative-layout`。`AssetRoot` 指 `editable_gripper_preview` 目录。其他项目传入这一根目录即可；`manifest.json` 内全部资产路径相对于 `AssetRoot`，不依赖当前工作目录。

两种型号初始展示均为房顶朝上，柔性导线伸直。展示朝向由相机控制，CAD / GLB 坐标约定保持一致。

## 数据约定

- 型号：`12` 或 `32`，分别有 23 / 43 个具名组件，器件数量为 12 / 32。
- 房顶方向：封装尖端为原始 CAD +Y。两型号 XY 点位直接来自 CSV，编号只为来源标识，不决定排列。CSV +Y 映射到 CAD +Y，默认展示向上。
- 精确曲面：STEP，单位 mm，保持原始 STEP 的 XYZ 右手坐标。
- 爆炸参数：Python / Blender 使用 0～1，HTML 使用 0～100%。0 均为装配状态。
- 爆炸位移：清单中的 `explode_translation_cad_mm` 是完全展开时在 CAD 坐标中的平移向量；单件 STEP 保持装配位置。
- 浏览器显示变换：`preview=(-CAD.x, 14-CAD.y, CAD.z+12)`。`model_api.load_mesh()` 已转换回原始 CAD 坐标，不要再旋转一次。
- Blender 导入按当前场景的实际单位比例将 mm 换成场景单位。所有零件挂在一个父对象下，移动父对象即可与其他模型装配。
- GLB 保存装配状态，单位为米，按 glTF 标准 Y 向上导出；Blender 标准导入器会恢复坐标方向。

稳定零件 ID：`Structural_body`、`Source_cover`、`Silicone_cap`、`PCB_illustrative`、`Solder_pads_illustrative`、`Connector_illustrative`、`Connector_pins_illustrative`、`Sensor_01_illustrative` …、`Wire_1_illustrative` …。传感器、焊盘、端子和线缆在总装 STEP 内是具名组件；单独 STEP 是否存在以清单的 `step_file` 为准。

## Blender：添加到已有场景

```python
from pathlib import Path
import sys

assets = Path(r"D:\2026\2026-1-THU-G1-mems_tactile_repeatedExperiments\（7）3D建模\editable_gripper_preview")
sys.path.insert(0, str(assets / "interface"))
from import_blender import import_model, set_explode, export_glb

module = import_model(channel=32, explode=0, asset_root=assets)
module.location = (0.2, 0, 0)  # 当前 Blender 场景单位
set_explode(module, 0.8)
silicone = next(o for o in module.children if o["part_id"] == "Silicone_cap")
# export_glb(module, r"D:\OtherProject\gripper.glb")
```

`import_model()` 不清空已有场景，不修改场景单位，返回父 Empty。子对象有稳定的 `part_id` 自定义属性；即使重复导入导致 Blender 给名字加 `.001`，仍可通过该属性查找。爆炸驱动控制子对象位置，整体定位使用父对象。

不写代码时，直接打开 `../blender/gripper-32.blend`；也可在其他 Blender 文件中通过 **File → Append** 追加它的 `Gripper_32` Collection。父对象的自定义属性 `explode` 已保存驱动关系。

命令行导入（`blender.exe` 换成实际安装路径）：

```powershell
$assets = 'D:\2026\2026-1-THU-G1-mems_tactile_repeatedExperiments\（7）3D建模\editable_gripper_preview'
blender.exe --background --factory-startup --python-exit-code 1 --python "$assets\interface\import_blender.py" -- --channel 32 --explode 0.8 --save 'D:\OtherProject\gripper.blend'
```

## SolidWorks：STEP 导入

需要本机安装并激活 SolidWorks。PowerShell 脚本按清单解析路径，调用 `GetImportFileData` → `MapConfigurationData=True` → `LoadFile4`，返回 `ModelDoc2` COM 对象；不自动覆盖或保存已有用户文件。

在 **Windows PowerShell 5.1** 中：

```powershell
$assets = 'D:\2026\2026-1-THU-G1-mems_tactile_repeatedExperiments\（7）3D建模\editable_gripper_preview'

# 只解析路径，无需安装 SolidWorks。
& "$assets\interface\Import-SolidWorks.ps1" -Channel 32 -State assembled -ResolveOnly

# 打开完整装配。
$doc = & "$assets\interface\Import-SolidWorks.ps1" -Channel 32 -State assembled

# 打开爆炸 STEP 或只调用胶层。
# $doc = & "$assets\interface\Import-SolidWorks.ps1" -Channel 12 -State exploded
# $doc = & "$assets\interface\Import-SolidWorks.ps1" -Channel 32 -PartId Silicone_cap
```

VBA 入口位于 `ImportGripper.bas`。在 SolidWorks 宏编辑器中导入该模块，其他 VBA 代码可以调用：

```vb
Dim model As Object
Set model = OpenGripper(Application.SldWorks, AssetRoot, 32, "assembled")
' 只调用胶层：
' Set model = OpenGripper(Application.SldWorks, AssetRoot, 32, "assembled", "Silicone_cap")
```

如需直接运行模块的 `main`，将新建 `.swp` 保存到本 `interface` 目录，宏会自动查找根目录。STEP 的导入拓扑受 SolidWorks 设置影响，可能显示为装配体或多实体零件；可使用五类单件 STEP 建立装配。接口不生成原生草图特征树或原生爆炸配置。

本机未安装 SolidWorks：COM/VBA 路径尚未实机运行。STEP 已重新导入 CAD 内核检查，PowerShell 的清单及路径解析已测试。

## 普通 Python / 其他建模程序

`model_api.py` 只依赖 Python 标准库，返回 STEP 路径、独立网格和元数据：

```python
import sys
from pathlib import Path

assets = Path(r"D:\2026\2026-1-THU-G1-mems_tactile_repeatedExperiments\（7）3D建模\editable_gripper_preview")
sys.path.insert(0, str(assets / "interface"))
from model_api import get_step_path, load_mesh, list_parts, load_manifest

step = get_step_path(32, part_id="Silicone_cap", asset_root=assets)
assembly = get_step_path(32, state="assembled", asset_root=assets)
mesh = load_mesh(32, explode=0, units="mm", asset_root=assets)
parts = list_parts(32, asset_root=assets)
# mesh["parts"][i] 包含 id、vertices、triangles、分类和爆炸位移。
# CadQuery 可继续调用：cq.importers.importStep(str(step))
```

CLI：`python model_api.py --channel 32 --part Silicone_cap`。用 `--list-parts` 输出完整清单。

## HTML 调用

打开 `../gripper-preview.html`，在该页面上下文中：

```javascript
window.gripperPreview.setModel(32);
window.gripperPreview.setExplode(80); // 0～100，百分比
window.gripperPreview.setVisibility('silicone', true);
window.gripperPreview.setView('side'); // iso / front / back / side
window.gripperPreview.getState();
```

iframe 嵌入后直接访问 `contentWindow` 需要同源；本版不提供跨域消息协议。离线 HTML 已内嵌模型，展示不依赖 Blender、SolidWorks 或服务器。

## 重建与验证

只改 HTML：在 `AssetRoot` 运行 `python build_preview.py`。它从当前网格生成页面并更新接口清单。

修改几何参数后依次运行：

```powershell
python build_models.py
python verify_cad.py
blender.exe --background --factory-startup --python-exit-code 1 --python interface/build_blender_assets.py
node verify_preview.cjs
python interface/verify_delivery.py
```

CAD 使用 `requirements-cad.txt` 依赖，Blender 使用自带 Python。`verify_preview.cjs` 使用 Playwright，文件开头的依赖路径可按目标机器环境调整。`build_blender_assets.py` 会清空其运行进程的场景，只允许在新建的后台 Blender 进程运行；向已有场景添加模型使用 `import_blender.py`。

`blender-validation.json` 记录 Blender 版本、零件数量、坐标/爆炸误差及 `.blend`/GLB 回读结果。`delivery-validation.json` 核对相对路径、原始文件哈希、单位和坐标转换，并检查 Blender 产物是否对应当前网格。

接口依据：[Blender Mesh API](https://docs.blender.org/api/5.0/bpy.types.Mesh.html)、[Blender 单位定义](https://docs.blender.org/api/5.0/bpy.types.UnitSettings.html)、[SolidWorks STEP 导入 API 示例](https://help.solidworks.com/2024/english/api/sldworksapi/Import_STEP_File_Example_VB.htm)。
