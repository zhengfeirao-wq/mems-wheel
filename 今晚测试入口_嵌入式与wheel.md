# 今晚测试入口：固件0x21 + tactile500 0.3.0

**最新烧录入口：[OSR256固件与步骤](嵌入式代码/Applications/Tactile500/烧录_OSR256_20260910/先读我_OSR256烧录.md)。压力/温度均已改为256，等用户烧录后再测。以下是早先OSR2048交付记录；网页服务已在后续手动测试中启动，不要重复启动占用USB。**

2026-09-10。一个wheel提供两种入口：Python采集API/CLI，以及Windows浏览器四板查看。
采集、原始录制保持每板实际500Hz接收；查看约10Hz。G1独立环境已装好。

1. **烧录工程**：[Tactile500.uvprojx](嵌入式代码/Applications/Tactile500/Project/MDK/Tactile500.uvprojx)
2. **main.c**：[Source/main.c](嵌入式代码/Applications/Tactile500/Source/main.c)
3. **按实物选Target/HEX**：[四板烧录说明](嵌入式代码/先读我_四板首次烧录.md)
4. **Python wheel**：[tactile500-0.3.0-py3-none-any.whl](gpt6-tactile500_pyusb上位机/wheelhouse/tactile500-0.3.0-py3-none-any.whl)
5. **启动与录制步骤**：[0.3.0交付说明](gpt6-tactile500_pyusb上位机/docs/RELEASE_0_3_0.md)
6. **测试证据**：[验收结果](gpt6-tactile500_pyusb上位机/reports/release_0_3_0/验收结果.md)
7. **完整通信协议**：[PROTOCOL_V2.md](嵌入式代码/Applications/Tactile500/docs/PROTOCOL_V2.md)

短线=新版，长线=旧版。左12、右12、左32短、右32短应分别显示08、09、0E、0F。

四板模拟已测；当前两块实物开启查看和录制连续约150秒，各约500Hz，
序号缺口、稳态坏帧、USB输入队列丢块、录制丢弃均0。
四块实物同时运行、通道按压响应和ADC新转换率仍待现场验收。
左12原始ch12当前固定471797，今晚重点按压。

测试进程均已结束，不占用USB。烧好接齐后，在G1执行：

```bash
cd /home/agi/tactile500_release_20260910_03
.venv/bin/tactile500 scan
.venv/bin/tactile500 view --bind 0.0.0.0 --port 8875 --output-root captures
```

随后Windows打开 `http://10.42.0.101:8875`（当前已核实的G1地址）。
也可执行上位机目录的[打开G1四板查看.ps1](gpt6-tactile500_pyusb上位机/打开G1四板查看.ps1)。
服务未启动时显示无法连接是正常的；无需重新安装或先运行旧版网页程序。
