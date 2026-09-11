# 线协议 V2 与录制格式 V2

所有多字节数值为小端。串口配置 921600、8 数据位、无校验、1 停止位。配套 MCU
120MHz / APB1 60MHz，实际 UART 整数分频约为 923076.9 bit/s（相对配置值 +0.16%）。

## UART 帧

| 字节偏移 | 长度 | 字段 |
|---|---:|---|
| 0 | 2 | 同步字 A5 5A |
| 2 | 1 | 总帧长 `20 + 5*N`，12 路 80，32 路 180 |
| 3 | 1 | 高 4 位协议主版本 2，低 4 位固件修订；当前 0x21 |
| 4 | 1 | identity：bit0 右1/左0；bit1 32路1/12路0；bit2 短线1/长线0；bit7:3 映射版本 |
| 5 | 1 | 状态位 |
| 6 | 4 | uint32 sequence，每个 2ms 计划槽位递增，漏发也递增 |
| 10 | 4 | uint32 sample_time_us，该帧 SPI 扫描开始时 MCU 微秒时钟 |
| 14 | 4 | uint32 fresh_mask，bit0 对应通道1 |
| 18 | 2*N | N 个 int16 温度，单位 0.1°C |
| 18+2*N | 3*N | N 个有符号 int24 压力，原有 `raw*9/80` 尺度 |
| 18+5*N | 2 | CRC-16/CCITT-FALSE，前面全部字节（含帧头）参与 |

CRC 参数：多项式 0x1021，初值 0xFFFF，RefIn/RefOut=false，XorOut=0；CRC 低字节先传。
校验向量 `123456789 → 0x29B1`。12 路 bit2 必须为 0，此时线缆解释为 none。

映射版本 1 的身份：左12=08、右12=09、左32长=0A、右32长=0B、左32短=0E、右32短=0F。
没有唯一硬件序列号。同一种身份的两块板不能仅从协议区分用途，因此实时快照报告 ambiguous。

状态字：bit0 并非所有通道 fresh；bit1 SPI 错误；bit2 传感器诊断错误；bit3 初始化读回错误；
bit4 扫描超时、bit5 TX 忙、bit6 TX 错误、bit7 定时器迟到是上电后锁存位。
fresh=1 仅表示读前 DRDY=1 且本次读成功；当前 DAC 模式的 DRDY=0 不等于数据不可读取。
温度无效值 -32768，压力无效值 -8388608，不能当有效测量值处理。

MCU 微秒时间约 71.6 分钟回绕。对差值取模 2^32；小于 2^31 的前向增量视为正常，
更大的倒向变化视为重启/乱序，不能算成几十亿个丢包。跨断线较长时间不保证回绕判别唯一，
应使用连接 epoch 和主机日志共同判断。不同 MCU 上电时间不同，其时间戳不能直接比较。

## .t5raw 文件

每条 USB 路径、连接/重启代数、身份组合写一个文件，文件名带路径和 epoch。独立于旧 T500
格式，旧解析器不能读取。文件头：8 字节 `T5V2RAW\0`，4 字节无符号小端 JSON 长度，随后
UTF-8 JSON。JSON 包含 `format_version=2`、path、role、identity、wire_version、采集机器
原始 UTC 时间和时钟语义。长度上限 65536 字节。

其后每条记录：

| 偏移 | 类型 | 内容 |
|---|---|---|
| 0 | uint64 LE | host_read_end_ns |
| 8 | uint64 LE | host_read_start_ns |
| 16 | uint32 LE | epoch |
| 20 | uint16 LE | UART 原帧长度（80 或 180） |
| 22 | uint16 LE | flags：gap=1、duplicate=2、reset=4、batched=8 |
| 24 | 原帧长度字节 | 完整 UART V2 帧，包含自身 CRC |

异步模式 start_ns 是请求提交时刻，end_ns 是完成回调时刻；在途请求含排队等待。
单个原始帧可能跨多个 USB 请求，记录的是完成该帧的那个请求。不得用这两个主机时刻
声称测出了 ADC 时间或精确 UART 传输时延。

`session.json` 保存文件清单、写入条数、录制队列丢弃、错误和终止后状态；`report.json`
另包含停止前在线状态、墙上经过时长（单调时钟）和进程 CPU 消耗。
停止后 connected=false 属于正常释放设备，不表示测试途中断线。

`read_recording()` 流式读回并验证记录长度、格式版本和每帧 CRC；尾部不完整会显式报错。
只保存 CRC 有效的帧，因此需结合报告中的坏帧/缺口/丢弃计数判断链路完整性，不能仅凭
录制文件内所有 CRC 正确就声称传输从未丢包。

## 实现依据

协议以相邻固件的 `docs/PROTOCOL_V2.md` 和编码器为准。高速 USB 实现依据
[libusb 异步 I/O 文档](https://libusb.sourceforge.io/api-1.0/group__libusb__asyncio.html)，
复用 [PyUSB 1.3.1 libusb1 后端定义](https://github.com/pyusb/pyusb/blob/v1.3.1/usb/backend/libusb1.py)。
固定依赖版本，避免内部 ctypes 布局随升级变化。
