# 0.3.0 今晚测试交付

日期：2026-09-10。固件保持已构建的V2修订0x21；Python包为tactile500 0.3.0。
一个wheel包含采集API与可选查看界面。不运行view时，核心不加载网页服务。
Windows浏览器只访问G1上的查看服务；USB接收、解码和原始数据文件均在G1。

## 已准备的入口

- [安装包](../wheelhouse/tactile500-0.3.0-py3-none-any.whl)
- [离线依赖PyUSB 1.3.1](../wheelhouse/pyusb-1.3.1-py3-none-any.whl)
- [固件Keil工程](../../firmware_tactile500/Project/MDK/Tactile500.uvprojx)
- [按四块实物选择HEX](../../firmware_tactile500/先读我_四板首次烧录.md)
- [MCU完整通信协议](../../firmware_tactile500/docs/PROTOCOL_V2.md)

G1已经建立独立环境：`/home/agi/tactile500_release_20260910_03/.venv`。
此前0.2.0实验目录与机器人应用环境保留。SSH 地址形如
`agi@<G1-IP>`（把 `<G1-IP>` 换成机器人当前实际地址）；换网络后需重新确认。

在G1终端中执行：

```bash
cd /home/agi/tactile500_release_20260910_03
.venv/bin/tactile500 scan
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
```

Windows浏览器打开 `http://<G1-IP>:8875`。板卡烧录后上电自动输出，主机无需发送启动命令。
软件以线上身份选择左12、右12、左32、右32；右侧实物尚未接上时显示未检测到。
界面有全部88个通道的压力变化量和温度、选中通道趋势、收包率、数据年龄、缺口和坏帧。
点击通道可在详情中核对显示位置与MCU通道。短线新版使用用户确认的32点位置表；
长线或未知映射保留原始通道并明确提示位置未确认。

点击“开始原始录制”后，G1的captures下创建唯一目录，包含各设备的t5raw与session.json。
点击“停止并保存”只停止此次录制，采集和显示继续；Ctrl+C结束整个服务并保存余下记录。
在G1可用以下命令重新逐帧验证CRC、帧数和缺口：

```bash
.venv/bin/tactile500 inspect captures/<界面显示的目录名>
```

G1日历时间目前与Windows不同；目录名沿用G1本地时间并带随机后缀，
测试报告另用Windows日期标识。速率与数据年龄采用单调时钟，不依赖日历时间。

## 接入Python系统

```python
from tactile500 import TactileSystem

system = TactileSystem()
frames = system.subscribe(capacity=8192)
system.open()
try:
    while True:
        item = frames.get(timeout=1)
        f = item.frame
        # 原始通道顺序；每块实物每个完整帧单独交付。
        consume(f.role, f.sequence, f.temperature, f.pressure, f.fresh_mask)
finally:
    system.close()
    frames.close()
```

如需在已有TactileSystem上增加查看，可复用同一对象创建
`Monitor(system, Path("captures"))`，并用`make_server`启动HTTP；
不要同时启动另一份独立view/capture进程抢占同一CH340。
原始Python接口和录制没有按10Hz降采样。500Hz快照不是同步ADC采样保证，
接口详细说明见[API文档](API_AND_INTEGRATION.md)。

## 显示与采集速率

- 原始USB层持续异步读取，独立解码；原始录制采用有界队列与独立写盘线程。
- 查看服务每100ms生成一次JSON缓存，HTTP请求只读缓存，不向采集层新增订阅。
- 浏览器约10Hz更新，曲线保留20秒抽样趋势，不能用于读取2ms级瞬态峰值；分析用t5raw。
- 主机收包率为近期约1秒统计；详情另有全程主机平均值和MCU时间戳推算值。
- 累计序号缺口、稳态坏帧、重复、USB输入队列丢块和录制丢弃分别显示/记录。
- 断线、数据过期、身份冲突会明确显示，不把无数据的板子画成正常运行。
- 压力尚未标定为N或Pa，界面基线只改变显示，不改传输值或文件。
- fresh=0的现有行为保持；不能把完整帧500Hz说成每通道500次新ADC转换。

四板UART有效负载理论总和是260,000字节/秒，原始录制每帧另加24字节主机元数据，
四板约308,000字节/秒，约1.11GB/小时（十进制，另有少量头部）。
G1空间有限，长时间录制前检查目标盘容量。HTTP流量另行实测列在性能报告中。

## 今晚烧录后的检查

1. 四块板分别选择正确Target：左12=08、右12=09、左32短=0E、右32短=0F。
2. 烧录Verify后正常运行、接入Hub；先枚举再查看身份和数据。
3. 四角色在线后录制至少60秒，核对约500帧/秒、序号缺口0、稳态坏帧0和录制丢弃0。
4. 逐点按压核对32点映射；特别检查左12原始ch12此前恒定471797是否响应。
5. 实物四板稳定后，再安排长时间测试及ADC新转换率测量。

查看服务默认仅监听127.0.0.1；上述0.0.0.0命令用于本次可信实验局域网。
它没有用户登录功能，不用于公网部署。录制控制有同源与随机请求令牌检查。
默认使用8875端口，避开G1已经占用的8765。Windows直接USB采集未列入本次实机验收范围。
