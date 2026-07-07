<#
.SYNOPSIS
    시험에서 생성된 Final Data 파일을 지정 폴더로 복사하는 스크립트

.DESCRIPTION
    LSWT 시험에서 생성된 데이터 파일(예: T0299R0032_FinalSet.dat)을
    Source 폴더에서 Target 폴더로 복사한다.
    복사할 Run 번호는 콤마(,)와 범위(-)로 지정한다.

    Root 폴더 위치, 시험 Code, 파일명 형식은 아래 [사용자 설정] 구역의
    변수를 수정하여 변경할 수 있다.

.PARAMETER Runs
    복사할 Run 번호 목록. 콤마로 구분하며 범위 지정 가능.
    예: "10,11,15-21"

.EXAMPLE
    .\Copy-TestData.ps1 -Runs "10,11,15-21"

.EXAMPLE
    .\Copy-TestData.ps1 32
    (Run 32 하나만 복사)

.EXAMPLE
    .\Copy-TestData.ps1 -Runs "15-21" -WhatIf
    (실제 복사 없이 어떤 파일이 복사될지 미리 확인)
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory = $true, Position = 0,
               HelpMessage = "복사할 Run 번호를 입력하세요. 예: 10,11,15-21")]
    [string]$Runs
)

# ============================================================================
# [사용자 설정] 필요시 아래 변수를 수정
# ============================================================================
$TestCode   = 'T0299'                  # 이번 시험에서 지정된 code
$SourceRoot = 'D:\LSWT\Test_Data'      # Source root 폴더
$TargetRoot = 'X:\LSWT\Test_Data'      # Target root 폴더

# 시험 code 기준으로 실제 source/target 폴더 구성
$SourceFolder = Join-Path $SourceRoot "$TestCode\Final_Data"
$TargetFolder = Join-Path $TargetRoot "$TestCode\Etc\KariToKAL"

# 파일명 형식: {0}=시험 code, {1}=Run 번호(4자리) → 예: T0299R0032_FinalSet.dat
$FileNameFormat = '{0}R{1:D4}_FinalSet.dat'
# ============================================================================

# Run 번호 문자열("10,11,15-21")을 숫자 배열로 변환
function ConvertTo-RunNumbers {
    param([string]$Spec)

    $numbers = New-Object System.Collections.Generic.List[int]

    foreach ($token in ($Spec -split ',')) {
        $token = $token.Trim()
        if ($token -eq '') { continue }

        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            # 범위 지정 (예: 15-21)
            $start = [int]$Matches[1]
            $end   = [int]$Matches[2]
            if ($start -gt $end) {
                throw "잘못된 범위 지정: '$token' (시작 번호가 끝 번호보다 큽니다)"
            }
            foreach ($n in $start..$end) { $numbers.Add($n) }
        }
        elseif ($token -match '^\d+$') {
            # 단일 번호 (예: 10)
            $numbers.Add([int]$token)
        }
        else {
            throw "잘못된 Run 번호 형식: '$token' (사용 예: 10,11,15-21)"
        }
    }

    if ($numbers.Count -eq 0) {
        throw "복사할 Run 번호가 없습니다. (입력값: '$Spec')"
    }

    return @($numbers | Sort-Object -Unique)
}

# ----------------------------------------------------------------------------
# 사전 확인
# ----------------------------------------------------------------------------
$runNumbers = ConvertTo-RunNumbers -Spec $Runs

if (-not (Test-Path -LiteralPath $SourceFolder -PathType Container)) {
    Write-Error "Source 폴더를 찾을 수 없습니다: $SourceFolder"
    exit 1
}

if (-not (Test-Path -LiteralPath $TargetFolder -PathType Container)) {
    Write-Host "Target 폴더가 없어 새로 생성합니다: $TargetFolder"
    New-Item -ItemType Directory -Path $TargetFolder -Force | Out-Null
}

Write-Host ""
Write-Host "시험 Code : $TestCode"
Write-Host "Source    : $SourceFolder"
Write-Host "Target    : $TargetFolder"
Write-Host "Run 번호  : $($runNumbers -join ', ')  (총 $($runNumbers.Count)개)"
Write-Host ""

# ----------------------------------------------------------------------------
# 복사 실행
# ----------------------------------------------------------------------------
$copied  = 0
$missing = @()

foreach ($run in $runNumbers) {
    $fileName   = $FileNameFormat -f $TestCode, $run
    $sourcePath = Join-Path $SourceFolder $fileName

    if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
        if ($PSCmdlet.ShouldProcess($fileName, "복사")) {
            Copy-Item -LiteralPath $sourcePath -Destination $TargetFolder -Force
            Write-Host ("[복사 완료] {0}" -f $fileName) -ForegroundColor Green
        }
        $copied++
    }
    else {
        Write-Host ("[파일 없음] {0}" -f $fileName) -ForegroundColor Yellow
        $missing += $fileName
    }
}

# ----------------------------------------------------------------------------
# 결과 요약
# ----------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================"
Write-Host ("복사 완료 : {0}개" -f $copied)
Write-Host ("파일 없음 : {0}개" -f $missing.Count)
if ($missing.Count -gt 0) {
    Write-Host "----------------------------------------"
    Write-Host "Source 폴더에 없는 파일:"
    $missing | ForEach-Object { Write-Host "  - $_" }
}
Write-Host "========================================"
