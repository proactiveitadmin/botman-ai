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

# 1. Wczytaj JSON
$jsonText = Get-Content -LiteralPath $SeedFile -Raw -Encoding UTF8
$rootObj  = $jsonText | ConvertFrom-Json

# 2. Root key w pliku (np. "Campaigns")
$oldRootKey = $rootObj.PSObject.Properties.Name | Select-Object -First 1
$items      = $rootObj.$oldRootKey

Write-Host "Root key in seed file : $oldRootKey"

# 3. Ustaw pk + body dla każdego itemu
foreach ($entry in $items) {
    $item = $entry.PutRequest.Item

    # --- PK ---
    if (-not $item.pk) {
        $campaignId = $item.campaign_id.S
        $tenantId   = $item.tenant_id.S

        if ($tenantId) {
            $pkValue = "$tenantId#$campaignId"
        } else {
            $pkValue = $campaignId
        }

        Write-Host "  -> setting pk = '$pkValue' for campaign_id='$campaignId'" -ForegroundColor Cyan
        $item | Add-Member -Name 'pk' -Value @{ S = $pkValue } -MemberType NoteProperty
    }

    # --- BODY ---
    # jeśli body.NULL == true => zamień na body.S z jakimś tekstem
    if ($item.body -and $item.body.PSObject.Properties.Name -contains 'NULL' -and $item.body.NULL -eq $true) {
        $campaignId = $item.campaign_id.S
        $bodyText   = "Sample body for $campaignId"

        Write-Host "  -> setting body = '$bodyText'" -ForegroundColor Yellow
        $item.body = @{ S = $bodyText }
    }
}

# 4. Zbuduj payload z root key równym nazwie tabeli
$payloadObj = [ordered]@{}
$payloadObj[$TableName] = $items

# 5. Zapisz jako JSON (ddb-JSON) UTF-8 bez BOM
$jsonOut   = $payloadObj | ConvertTo-Json -Depth 20 -Compress
$tmpFile   = [System.IO.Path]::GetTempFileName()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpFile, $jsonOut, $utf8NoBom)

Write-Host "Using paramfile: $tmpFile"
Write-Host ""

aws dynamodb batch-write-item `
    --region $Region `
    --request-items ("file://{0}" -f $tmpFile)

Remove-Item $tmpFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Seeding completed." -ForegroundColor Green
