# 软件校零（tare）

**把静止基线从压力值里减掉，让"未接触"时读数接近 0；同时完整保留原始值，可随时还原。**

面向调用方（你的采集系统插件）：在每次开始采集前调用一次 `measure_baseline()`，
之后用 `TareFilter` 处理订阅到的帧即可。

---

## 三条铁律

| # | 规则 | 为什么 |
|---|---|---|
| 1 | **原始值永不修改** | `frame.pressure` 始终是固件原值；校零只是"视图" |
| 2 | **每次校零都留档** | 追加式 JSONL，可事后统计多天的零点漂移 |
| 3 | **坏通道不静默处理** | 饱和/无数据的通道给 0 偏移并标记，不假装修好了 |

---

## 快速开始

```python
from tactile500 import TactileSystem
from tactile500.tare import measure_baseline, TareFilter, TareJournal

system = TactileSystem()
native = system.subscribe(capacity=16384)
system.open()

# ① 采集系统启动时：夹爪张开、无接触，采 2 秒基线
result = measure_baseline(system, seconds=2.0)
for w in result.warnings:
    print("校零警告:", w)

# ② 留档（可回溯、可看长期漂移）
TareJournal().append(result, note="第 1 天开机")

# ③ 之后所有输出都从校零后的值取
tared = TareFilter(result)
while True:
    item = native.get(timeout=1.0)
    frame = item.frame
    shown = tared.apply_frame(frame)   # 0 附近
    raw = frame.pressure               # 原始值，一直都在
```

---

## API

### `measure_baseline(system, *, seconds=2.0, roles=None, fresh_only=True, min_samples=50, max_spread=20000, reject_saturated=True, capacity=8192, max_frames=40000) -> TareResult`

采集静止基线。**调用方必须保证夹爪空载**——本函数只能靠"数值是否稳定"兜底提示。

| 参数 | 说明 |
|---|---|
| `seconds` | 基线时长，建议 1~3 秒 |
| `roles` | 只校这些角色（`left_palm` / `left_fingers` / `right_palm` / `right_fingers`）；`None` = 全部 |
| `fresh_only` | **稳定性评估只用 `fresh_mask` 命中的帧**（那些才是真新转换） |
| `min_samples` | 少于该帧数判为 `no_data` |
| `max_spread` | 极差超过它判为 `unstable` |
| `reject_saturated` | 是否拒绝顶到满量程的通道 |

它自己开一个订阅、采完就关，**不影响你自己的订阅**。

### `TareResult`

```python
result.offsets          # {role: (每通道偏移,)}
result.baselines        # {role: (ChannelBaseline,)}  含 offset/spread/samples/status
result.identities       # {role: identity 整数}
result.warnings         # 人类可读的警告
result.created_iso      # ISO 时间戳
result.to_json()        # 可序列化，供持久化
TareResult.from_json(d)
```

### `TareFilter(result, *, strict=False)`

```python
f.apply(role, pressure)      # 按角色校零
f.apply_frame(frame)         # 便捷入口
f.offsets_for(role)
TareFilter.raw(frame)        # 永远能拿回原始值
restore(tared, offsets)      # 把校零值还原成原始值
```

---

## 通道状态判定

| status | 条件 | 偏移取值 | 含义 |
|---|---|---|---|
| `ok` | 样本够、极差 ≤ `max_spread` | 中位数 | 正常 |
| `unstable` | 极差 > `max_spread` | 中位数 | **夹爪可能没空载**，或通道噪声大 |
| `saturated` | 中位数或极值顶到 ±943718 | **0** | 24 位 ADC 到端点，硬件/接线问题 |
| `no_data` | 样本不足，或全是哨兵 −8388608 | **0** | 设备没在线或通道未就绪 |

**为什么用中位数而不是均值**：本系统存在满量程尖峰（如左手 12 点 ch0 会跳到 −943718），
均值会被单个尖峰拉偏几百个单位，中位数不受影响。

**为什么稳定性用 fresh 帧算**：500 Hz 帧率下单次转换约 250 Hz，非 fresh 帧是重复值，
用它们算极差会低估真实波动。

---

## 档案与漂移回溯

每次校零追加一行到 `~/.tactile500/tare/journal.jsonl`：

```python
journal = TareJournal()            # 或 TareJournal(自定义路径)
journal.append(result, note="第 3 天开机")
journal.history(identity="0x0A")   # 按时间顺序
journal.latest(identity="0x0A")
journal.drift(identity="0x0A")     # 某块板的零点随时间变化
```

命令行工具：

```bash
python tools/tare_journal.py show                     # 列出全部记录
python tools/tare_journal.py drift 0x0A               # 每通道漂移（末次 − 首次）
python tools/tare_journal.py drift 0x0A --channel 1   # 单通道逐次漂移
python tools/tare_journal.py latest 0x0A --out t.json # 导出最新一次
python tools/tare_journal.py restore raw_left_big.csv t.json   # CSV 还原成原始值
```

按 **identity**（`0x08`/`0x09`/`0x0A`/`0x0B`）索引而非 USB 路径，**换 USB 口不失效**。

---

## 实测（2026-09-11，G2，四板）

```
right_fingers  12通道  ok=12  饱和=0
right_palm     32通道  ok=32  饱和=0
left_palm      32通道  ok=32  饱和=0
left_fingers   12通道  ok=11  饱和=1
⚠ left_fingers ch0 顶到满量程，已跳过（硬件/接线问题）

校零后残差：left_palm 最大 39 / right_palm 51 / right_fingers 404
还原验证：四板全部一致
原始值：frame.pressure 未被修改
```

---

## 边界与注意事项

1. **单位仍是"固件值"**，不是 Pa 也不是 N。校零后是**相对变化量**；绝对量纲需实物标定。
2. **一次性校零**，不做滑动基线。滑动基线会把缓慢变化的真实力当成漂移减掉——
   动态夹爪上很危险。需要重校时再调一次 `measure_baseline()`。
3. **温漂**：芯片 DSP 已做二阶温度补偿，残余漂移较小；长期漂移可由 journal 的 drift 曲线观察。
4. **不要用它代替芯片标定**。芯片标定系数在 EEPROM（`0xAE`~`0xBC`），本模块完全不碰。
5. 饱和通道（如 `left_fingers ch0`）**修不好就是修不好**——本模块只负责不让你误以为是零点。
