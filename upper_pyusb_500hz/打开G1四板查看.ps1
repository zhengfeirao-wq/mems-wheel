param(
    [string]$RobotAddress = "10.42.0.101",
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
