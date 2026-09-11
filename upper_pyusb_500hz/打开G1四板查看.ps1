param(
    # 机器人地址。在 G1 本机运行保持 localhost；从 Windows 远程查看时传入机器人 IP，
    # 例如： .\打开G1四板查看.ps1 -RobotAddress 192.168.1.100
    [string]$RobotAddress = "localhost",
    [int]$ViewPort = 8875
)
$viewUrl = "http://${RobotAddress}:${ViewPort}/"
try {
    $null = Invoke-WebRequest -Uri ($viewUrl + "api/snapshot") -TimeoutSec 4 -UseBasicParsing
    Start-Process $viewUrl
} catch {
    Write-Host "查看服务尚未连通：$viewUrl"
    Write-Host "请先在 G1 启动 tactile500 view，并确认当前机器人地址和网络。"
}
