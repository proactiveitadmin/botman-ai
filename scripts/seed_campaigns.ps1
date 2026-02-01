param(
    [Parameter(Mandatory = $true)]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [string]$TableName,  # np. Campaigns-botman-stage

    [Parameter(Mandatory = $true)]
    [string]$SeedFile
)

Write-Host "Region    : $Region"
Write-Host "TableName : $TableName"
Write-Host "SeedFile  : $SeedFile"
Write-Host ""

if (-not (Test-Path -LiteralPath $SeedFile)) {
    Write-Error "Seed file '$SeedFile' not found."
    exit 1
}

# === NOW ===
$nowTs = [int][double]::Parse((Get-Date -Date (Get-Date).ToUniversalTime() -UFormat %s))

# 1. Wczytaj JSON
$jsonText = Get-Content -LiteralPath $SeedFile -Raw -Encoding UTF8
$rootObj  = $jsonText | ConvertFrom-Json

# 2. Root key w pliku (np. "Campaigns")
$oldRootKey = $rootObj.PSObject.Properties.Name | Select-Object -First 1
$items      = $rootObj.$oldRootKey

Write-Host "Root key in seed file : $oldRootKey"
Write-Host "NOW (next_run_at)    : $nowTs"
Write-Host ""

foreach ($entry in $items) {
    $item = $entry.PutRequest.Item
    $campaignId = $item.campaign_id.S

    # =========================
    # PK (NOWY STANDARD)
    # =========================
    if (-not $item.pk) {
        $pkValue = "CAMPAIGN#$campaignId"
        Write-Host "  -> setting pk = '$pkValue'" -ForegroundColor Cyan
        $item | Add-Member -Name 'pk' -Value @{ S = $pkValue } -MemberType NoteProperty
    }

    # =========================
    # next_run_at (WYMAGANE)
    # =========================
    if (-not $item.next_run_at) {
        Write-Host "  -> setting next_run_at = $nowTs" -ForegroundColor Green
        $item | Add-Member -Name 'next_run_at' -Value @{ N = "$nowTs" } -MemberType NoteProperty
    }

    # =========================
    # schedule (WYMAGANE)
    # =========================
    if (-not $item.schedule) {
        Write-Host "  -> adding default schedule (interval 24h)" -ForegroundColor Green
        $item | Add-Member -Name 'schedule' -Value @{
            M = @{
                type = @{ S = "interval" }
                every_seconds = @{ N = "86400" }
                anchor = @{ S = "last_run" }
            }
        } -MemberType NoteProperty
    }

    # =========================
    # BODY fallback (jak było)
    # =========================
    if ($item.body -and $item.body.PSObject.Properties.Name -contains 'NULL' -and $item.body.NULL -eq $true) {
        $bodyText = "Sample body for $campaignId"
        Write-Host "  -> setting body fallback" -ForegroundColor Yellow
        $item.body = @{ S = $bodyText }
    }
}

# 4. Payload z root key = nazwa tabeli
$payloadObj = [ordered]@{}
$payloadObj[$TableName] = $items

# 5. JSON UTF-8 bez BOM
$jsonOut   = $payloadObj | ConvertTo-Json -Depth 30 -Compress
$tmpFile   = [System.IO.Path]::GetTempFileName()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpFile, $jsonOut, $utf8NoBom)

Write-Host ""
Write-Host "Using paramfile: $tmpFile"
Write-Host ""

aws dynamodb batch-write-item `
    --region $Region `
    --request-items ("file://{0}" -f $tmpFile)

Remove-Item $tmpFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Seeding completed successfully." -ForegroundColor Green
