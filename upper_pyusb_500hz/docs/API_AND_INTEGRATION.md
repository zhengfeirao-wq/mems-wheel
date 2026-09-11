# V2 API 与大系统集成

## 对象和职责

`TactileSystem(expected_roles=ROLES, scan_interval=0.5, stale_seconds=0.020,
no_data_seconds=2.0, usb_io="async")` 管理采集。构造不打开 USB；`open()` 启动后可先没有
任何板，随后插入自动发现。`close(timeout=8.0)` 停止读取并等待处理线程结束；同一对象
关闭后不能再次打开，需创建新对象。不要把 `system.status()` 当作实时流反复高频轮询。

`subscribe(capacity=8192)` 返回独立有界订阅。`get(timeout=...)` 没有数据时抛出标准
`queue.Empty`。消费者慢时丢弃其最旧数据，`subscription.dropped` 累计，其他订阅不受影响。
用户回调、机械臂控制和磁盘写入应在消费线程执行。`Recorder` 自带独立消费线程和 32768
帧队列，先关闭 system 再关闭 recorder 可以将剩余队列写完。

`ReceivedFrame` 不可变字段：

| 字段 | 意义 |
|---|---|
| frame | CRC 验证后的 `Frame` |
| path | 当前 USB 拓扑路径，仅作设备连接标识 |
| epoch | 该路径重连、MCU 重启或身份改变时增加的代数 |
| host_read_start_ns | 完成该帧的 USB 请求提交时刻（异步时包含在队列中等待的时间） |
| host_read_end_ns | 该请求完成回调被执行时的主机单调时刻 |
| flags | 位 0 序号缺口、位 1 重复、位 2 重置/倒序、位 3 同一次读取解析出多帧 |

主机时间戳不是 UART 硬件边沿时间。`host_read_end_ns - host_read_start_ns` 包含排队时间，
不能解释为 UART 传输耗时或传感器延迟。每板已预排队的请求按提交顺序交付；回调被主机
调度延迟时，仍保留 MCU 时间戳和序号，不伪造均匀的到达时间。

`Frame` 字段：`version`, `identity`, `status`, `sequence`, `sample_time_us`, `fresh_mask`,
`temperature`, `pressure`, `raw`。后两个数值数组是不可变 tuple；`raw` 为完整 V2 帧。
派生属性包括 `role`, `hand`, `channels`, `cable`, `mapping_revision`。

`status()` 返回每条路径的连接、身份、累计帧数、缺口、重复、重置、CRC 候选拒绝、输入队列
丢弃和各订阅丢弃。`host_received_rate_hz` 按首末帧主机时间计算，重连停顿计入平均值；
`mcu_received_rate_hz` 按同板 MCU 时间间隔计算；`mcu_scheduled_rate_hz` 还包含序号缺口。
MCU 重置后的时间间隔不跨越累加。总 `rejected_candidates` 可包括连接开始时的残片，
应结合 `startup_rejected_candidates` 与 `stream_rejected_candidates` 判断。

## 同一主机时间轴

`snapshot(target_ns=None, previous=None)` 选取每个角色在 `target_ns` 及之前最近收到的帧。
保留每路径最近 256 帧，目标早于历史缓存时返回 missing。`previous` 用于判断是否复用了
同一 `ReceivedFrame`。重复读的数值即使完全一样，也不能据此判定 ADC 没有转换。

`snapshots(hz=500, delay_seconds=0.004)` 在统一时间网格上产生 `Snapshot`，其中
`target_ns` 是目标主机时刻；`slots` 始终包含配置要求的角色。状态含义：

| 状态 | 上层处理建议 |
|---|---|
| updated | 本快照选择了新的接收帧；另看 fresh_mask 判断 ADC 新数据证据 |
| reused | 与上一快照相同的帧，不当成新的原始样本累计 |
| stale | 有历史帧，但接收年龄超过 20ms 默认阈值 |
| missing | 从未识别此角色，或目标时刻之前没有缓存帧 |
| offline | 曾识别到该角色，目前连接不可用 |
| ambiguous | 同角色存在多块在线板，不自动挑选 |

默认角色为左右各 12 路 fingers 和 32 路 palm；只用一只手时可传入
`expected_roles=("left_fingers", "left_palm")`。缺板并不妨碍其他角色出快照。

`receive_skew_ns` 是所有非 stale 的选中帧接收时刻的极差，少于两块时为 None。
同一网格解决上层时序接口的一致性；独立 MCU 的启动相位、ADC 转换相位和 USB 延迟仍存在。
没有共享触发线或 MCU 接收同步命令的实现时，软件无法证明严格同时采样。

## 故障边界和资源

每个路径持续以 0.1–2 秒退避重试，发现线程不等待单板打开成功。已知 USB 拓扑最多 64 个，
避免异常拓扑无限增生；超过时状态报告需要重启采集。输入队列每板 2048 个 USB 块，满时
丢最旧块并增加 `input_dropped_chunks`，解析器随后重新找帧头和 CRC。

异步读维护每板 32 个在途请求，典型读取长度为 12 路 64 字节 / 32 路 160 字节。
正常关闭先停止提交并等待在途请求自然完成；静默/故障才取消请求并处理取消回调，然后
释放内存和设备句柄，以保留末尾字节、减少不必要的取消。取消不能
完成时，保留仍被 C 层引用的对象并报告超时，避免释放仍在使用的缓冲区。

软件没有 Hub 供电控制，也不通过 reset_device 影响同 Hub 的其他板。总线供电 Hub
发生电气短路或上游断开时，所有板都可能掉线；程序在重新出现后按帧身份恢复。

## 物理位置与数值解释

`physical_values(frame)` 返回按物理位置排列的 `(temperature, pressure, fresh_mask)`。
32 路短线使用用户确认表；12 路维持通道 1–12 顺序；长线以及未知映射版本拒绝推断物理
布局。V2 固件已经执行片选顺序排列，不能再把同一排列应用一次。

无效哨兵为温度 `-32768`、压力 `-8388608`。传感器 fresh=0 本身不会清掉可读数值。
修订 0x21 的 DAC 连续模式实测 DRDY 全 0；当前不将这些帧宣称为每通道 500Hz 新转换。
原 OSR/滤波设置和 64 次压力后更新一次温度的工作模式也限制了实际更新率。
