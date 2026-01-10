param(
    [Parameter(Mandatory = $true)]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [string]$TableName,  # np. Tenants-botman-stage

    [Parameter(Mandatory = $true)]
    [string]$SeedFile,

    # Opcjonalnie: dopisz pole entity="TENANT" (przydaje się do listowania tenantów bez scana)
    [switch]$AddEntityTenant
)

Write-Host "Region    : $Region"
Write-Host "TableName : $TableName"
Write-Host "SeedFile  : $SeedFile"
Write-Host "AddEntity : $AddEntityTenant"
Write-Host ""

if (-not (Test-Path -LiteralPath $SeedFile)) {
    Write-Error "Seed file '$SeedFile' not found."
    exit 1
}

# 1) Read JSON
try {
    $jsonText = Get-Content -LiteralPath $SeedFile -Raw -Encoding UTF8
    $rootObj  = $jsonText | ConvertFrom-Json
} catch {
    Write-Error "Failed to parse JSON from '$SeedFile'. Error: $($_.Exception.Message)"
    exit 1
}

# 2) Root key (np. "Tenants")
$oldRootKey = $rootObj.PSObject.Properties.Name | Select-Object -First 1
if (-not $oldRootKey) {
    Write-Error "Seed file has no root key."
    exit 1
}

$items = $rootObj.$oldRootKey
if (-not $items) {
    Write-Error "Seed file root key '$oldRootKey' is empty."
    exit 1
}

Write-Host "Root key in seed file : $oldRootKey"
Write-Host "Items count           : $($items.Count)"
Write-Host ""

# 3) Validate & optional enrich
$idx = 0
foreach ($entry in $items) {
    $idx++

    if (-not $entry.PutRequest -or -not $entry.PutRequest.Item) {
        Write-Error "Item #${idx}: missing PutRequest.Item"
        exit 1
    }

    $item = $entry.PutRequest.Item

    if (-not $item.tenant_id -or -not $item.tenant_id.S) {
        Write-Error "Item #${idx}: missing tenant_id.S"
        exit 1
    }

    $tenantId = $item.tenant_id.S
    Write-Host "Tenant #${idx}: $tenantId" -ForegroundColor Cyan

    if ($AddEntityTenant) {
        if (-not $item.entity) {
            Write-Host "  -> adding entity=TENANT" -ForegroundColor Green
            $item | Add-Member -Name 'entity' -Value @{ S = "TENANT" } -MemberType NoteProperty
        } elseif ($item.entity.S -ne "TENANT") {
            Write-Host "  -> overwriting entity to TENANT (was '$($item.entity.S)')" -ForegroundColor Yellow
            $item.entity = @{ S = "TENANT" }
        }
    }
}

# 4) Build payload with root key = actual table name
$payloadObj = [ordered]@{}
$payloadObj[$TableName] = $items

# 5) Write temp JSON UTF-8 no BOM
$jsonOut   = $payloadObj | ConvertTo-Json -Depth 50 -Compress
$tmpFile   = [System.IO.Path]::GetTempFileName()
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpFile, $jsonOut, $utf8NoBom)

Write-Host ""
Write-Host "Using request-items file: $tmpFile"
Write-Host ""

# 6) BatchWrite
try {
    aws dynamodb batch-write-item `
        --region $Region `
        --request-items ("file://{0}" -f $tmpFile) | Out-Host
} catch {
    Write-Error "AWS CLI batch-write-item failed: $($_.Exception.Message)"
    Remove-Item $tmpFile -ErrorAction SilentlyContinue
    exit 1
}

Remove-Item $tmpFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Tenant seeding completed." -ForegroundColor Green
