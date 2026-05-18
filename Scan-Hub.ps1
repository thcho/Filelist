<#
.SYNOPSIS
    허브(같은 서브넷)에 연결된 장치의 IP를 찾는 PowerShell 스크립트.

.DESCRIPTION
    기본적으로 192.168.20.1 ~ 192.168.20.254 범위를 병렬로 핑(ping)하고,
    응답한 장치의 IP, MAC 주소(ARP 캐시), 호스트명(역방향 DNS)을 출력합니다.

.PARAMETER Subnet
    스캔할 /24 서브넷 접두사. (기본값: 192.168.20)

.PARAMETER Start
    시작 호스트 번호. (기본값: 1)

.PARAMETER End
    끝 호스트 번호. (기본값: 254)

.PARAMETER TimeoutMs
    핑 타임아웃(밀리초). (기본값: 500)

.PARAMETER NoHostname
    역방향 DNS 조회를 생략합니다.

.PARAMETER OutputFile
    결과를 저장할 텍스트 파일 경로 (선택).

.EXAMPLE
    .\Scan-Hub.ps1

.EXAMPLE
    .\Scan-Hub.ps1 -Subnet 192.168.20 -Start 1 -End 254 -OutputFile devices.txt
#>

[CmdletBinding()]
param(
    [string]$Subnet = '192.168.20',
    [ValidateRange(0, 255)]
    [int]$Start = 1,
    [ValidateRange(0, 255)]
    [int]$End = 254,
    [int]$TimeoutMs = 500,
    [switch]$NoHostname,
    [string]$OutputFile
)

# UTF-8 출력 설정 (한글 깨짐 방지)
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

if ($Start -gt $End) {
    Write-Error "Start($Start)는 End($End)보다 작거나 같아야 합니다."
    exit 1
}

# 서브넷 형식 검증
if ($Subnet -notmatch '^\d{1,3}\.\d{1,3}\.\d{1,3}$') {
    Write-Error "잘못된 서브넷 형식: $Subnet (예: 192.168.20)"
    exit 1
}

Write-Host "스캔 범위: $Subnet.$Start ~ $Subnet.$End"
Write-Host "타임아웃: ${TimeoutMs}ms"
Write-Host ('-' * 60)

# 병렬 핑 스윕 ---------------------------------------------------------------
$targets = $Start..$End | ForEach-Object { "$Subnet.$_" }

# System.Net.NetworkInformation.Ping 을 이용한 비동기 병렬 핑
Add-Type -AssemblyName System.Net

$pingers = @()
foreach ($ip in $targets) {
    $p = New-Object System.Net.NetworkInformation.Ping
    $task = $p.SendPingAsync($ip, $TimeoutMs)
    $pingers += [PSCustomObject]@{
        IP   = $ip
        Ping = $p
        Task = $task
    }
}

$alive = New-Object System.Collections.Generic.List[string]
foreach ($item in $pingers) {
    try {
        $reply = $item.Task.GetAwaiter().GetResult()
        if ($reply.Status -eq 'Success') {
            $alive.Add($item.IP) | Out-Null
            Write-Host "  [+] $($item.IP) 응답 ($($reply.RoundtripTime)ms)"
        }
    } catch {
        # 타임아웃/오류는 무시
    } finally {
        $item.Ping.Dispose()
    }
}

# IP 정렬 (옥텟 기준)
$aliveSorted = $alive | Sort-Object { [System.Net.IPAddress]::Parse($_).GetAddressBytes() | ForEach-Object { '{0:D3}' -f $_ } -join '.' }

# ARP 테이블 읽기 ------------------------------------------------------------
# 핑 직후 ARP 캐시에 MAC 주소가 남아있음.
$arpMap = @{}
try {
    if (Get-Command Get-NetNeighbor -ErrorAction SilentlyContinue) {
        Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -like "$Subnet.*" -and $_.LinkLayerAddress -and $_.LinkLayerAddress -ne '00-00-00-00-00-00' } |
            ForEach-Object {
                $arpMap[$_.IPAddress] = ($_.LinkLayerAddress -replace '-', ':').ToLower()
            }
    } else {
        # 폴백: arp -a 파싱
        $arpOutput = & arp -a 2>$null
        foreach ($line in $arpOutput) {
            if ($line -match '^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9A-Fa-f-]{17})\s+\S+') {
                $arpMap[$matches[1]] = ($matches[2] -replace '-', ':').ToLower()
            }
        }
    }
} catch {
    Write-Verbose "ARP 테이블 읽기 실패: $_"
}

# 결과 출력 ------------------------------------------------------------------
Write-Host ('-' * 60)

$results = foreach ($ip in $aliveSorted) {
    $mac = if ($arpMap.ContainsKey($ip)) { $arpMap[$ip] } else { '' }
    $hostname = ''
    if (-not $NoHostname) {
        try {
            $hostname = [System.Net.Dns]::GetHostEntry($ip).HostName
        } catch {
            $hostname = ''
        }
    }
    [PSCustomObject]@{
        IP       = $ip
        MAC      = $mac
        HostName = $hostname
    }
}

$summary = @(
    "스캔 범위: $Subnet.$Start ~ $Subnet.$End"
    "발견된 장치: $($aliveSorted.Count)대"
    ''
)

$tableText = if ($results) {
    $results | Format-Table -AutoSize | Out-String
} else {
    "(응답한 장치 없음)`n"
}

$finalOutput = ($summary -join "`n") + "`n" + $tableText.TrimEnd()
Write-Host $finalOutput

if ($OutputFile) {
    $finalOutput | Out-File -FilePath $OutputFile -Encoding utf8
    Write-Host ""
    Write-Host "결과가 '$OutputFile' 에 저장되었습니다."
}
