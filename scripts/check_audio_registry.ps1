$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Output "=== 会话类型（判断是否在远程桌面里）==="
query session
Write-Output ""

Write-Output "=== 录制端点 Capture（麦克风类）==="
Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture" | ForEach-Object {
  $state = (Get-ItemProperty $_.PSPath).DeviceState
  $props = Get-ItemProperty "$($_.PSPath)\Properties"
  $name = $props.'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
  $desc = $props.'{b3f8fa53-0004-438e-9003-51a46e139bfc},6'
  Write-Output ("state=0x{0:x}  {1}  [{2}]" -f $state, $name, $desc)
}
Write-Output ""

Write-Output "=== 播放端点 Render（扬声器/虚拟声卡输入端）==="
Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render" | ForEach-Object {
  $state = (Get-ItemProperty $_.PSPath).DeviceState
  $props = Get-ItemProperty "$($_.PSPath)\Properties"
  $name = $props.'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
  $desc = $props.'{b3f8fa53-0004-438e-9003-51a46e139bfc},6'
  Write-Output ("state=0x{0:x}  {1}  [{2}]" -f $state, $name, $desc)
}
