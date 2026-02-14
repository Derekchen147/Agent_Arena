# ========== 修正版：适配你的真实端口 ==========
# 【关键修改】替换成你查到的 Clash 实际端口！！！
# 这是解决问题的核心，按以下步骤操作（1 分钟搞定）：
# 打开 Clash Verge Rev 客户端；
# 点击左侧菜单栏的「设置」→ 选择「网络」标签（部分版本叫「代理设置」）；
# 找到「HTTP 代理」「SOCKS5 代理」对应的「监听端口」，记录下数字（比如 HTTP 端口可能是 7890/7892/10809 等）。
# 🔍 补充：如果找不到「网络」标签，也可以看 Clash Verge Rev 主界面的「系统代理」开关旁，Hover 鼠标会显示当前代理地址（比如 http://127.0.0.1:7892）。
$httpPort = "7897"  # 比如：7890/7892/10809
$socksPort = "7897"  # 比如：7891/7893/10808

# 设置代理（用你的真实端口）
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "https://127.0.0.1:7897"
$env:ALL_PROXY = "socks5://127.0.0.1:7897"

# 更严谨的验证（分步排查问题）
Write-Host "🔍 正在检测端口 $httpPort 是否被 Clash 占用..."
# 检测端口是否监听
$portCheck = netstat -ano | Select-String ":$httpPort\s+LISTENING"
if ($portCheck) {
    Write-Host "✅ 端口 $httpPort 已监听，进程ID：$($portCheck.ToString().Split()[-1])"
    # 验证代理连通性（换国内可访问的验证地址，避免墙的问题）
    Write-Host "🔍 验证代理连通性..."
    try {
        # 先测国内地址（确认网络本身没问题）
        Invoke-WebRequest -Uri "https://www.baidu.com" -TimeoutSec 5 | Out-Null
        Write-Host "✅ 本地网络正常"
        # 再测外网地址（确认代理生效）
        $response = Invoke-WebRequest -Uri "https://ipify.org" -TimeoutSec 10
        Write-Host "✅ 代理生效！出口IP：$($response.Content.Trim())"
    } catch {
        Write-Host "❌ 代理连通失败，原因：$($_.Exception.Message)"
        Write-Host "💡 排查建议：1. 确认 Clash 选了「全局」模式；2. 换一个可用的节点；3. 关闭防火墙"
    }
} else {
    Write-Host "❌ 端口 $httpPort 未监听！Clash 可能没启动，或端口查错了"
    Write-Host "💡 重新核对 Clash Verge Rev → 设置 → 网络 里的端口"
}