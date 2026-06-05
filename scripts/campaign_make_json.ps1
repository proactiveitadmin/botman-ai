param(
    [Parameter(Mandatory=$true)]
    [string]$TenantId,

    [Parameter(Mandatory=$true)]
    [string]$CampaignId,

    [Parameter(Mandatory=$true)]
    [string]$Key,

    # Podaj albo -PhoneNumbers albo -PhonesFile
    [string[]]$PhoneNumbers,

    [string]$PhonesFile,

    [string]$ProductId = "7",

    [ValidateSet("epoch","iso")]
    [string]$NextRunFormat = "epoch",

    [int]$RunInMinutes = 0,

    [string]$OutputFile = ".\scripts\campaign-generated.json"
)

#Add-Type -Path ".\bin\Debug\net8.0\Cryptography.Fernet.dll"

function Encrypt-Phone {
    param(
        [string]$TenantId,
        [string]$Phone,
        [string]$Key
    )

    $cmd = @"
from cryptography.fernet import Fernet
f = Fernet(b"$Key")
print(f.encrypt(b"$TenantId|$Phone").decode())
"@

    return python -c $cmd
}

function Normalize-Phone {
    param([string]$p)

    if (-not $p) { return $null }
    $p = $p.Trim()
    if ($p.Length -eq 0) { return $null }
    if ($p.StartsWith("#")) { return $null } # komentarz

    # Minimalna normalizacja: usuń spacje i myślniki, zostaw + i cyfry
    $p = $p -replace "\s+", ""
    $p = $p -replace "-", ""

    return $p
}

# ===== wczytaj numery =====
$phones = @()

if ($PhonesFile) {
    if (!(Test-Path $PhonesFile)) {
        throw "PhonesFile not found: $PhonesFile"
    }
    $phones += Get-Content $PhonesFile
}

if ($PhoneNumbers) {
    $phones += $PhoneNumbers
}

if (-not $phones -or $phones.Count -eq 0) {
    throw "Provide -PhoneNumbers or -PhonesFile"
}

$phonesNorm = $phones |
    ForEach-Object { Normalize-Phone $_ } |
    Where-Object { $_ -ne $null } |
    Select-Object -Unique

if ($phonesNorm.Count -eq 0) {
    throw "No valid phone numbers after normalization."
}

# ===== recipients =====
$recipientList = @()

foreach ($p in $phonesNorm) {
    $h = Encrypt-Phone -Phone $p -TenantId $TenantId -Key $Key

    $recipientList += @{
        M = @{
            token  = @{ S = $h }
        }
    }
}

# ===== keys + dates =====
$pk = "TENANT#$TenantId#CAMPAIGN#$CampaignId"
$createdAtIso = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
$nextRunIso   = (Get-Date).AddMinutes($RunInMinutes).ToString("yyyy-MM-ddTHH:mm:ss")

$campaign = @{
    pk         = @{ S = $pk }
    tenant_id   = @{ S = $TenantId }
    campaign_id = @{ S = $CampaignId }
    active      = @{ BOOL = $true }

    body = @{ S = "Hello {first_name}, your order is ready. {payment_link}" }

    payment_product_id       = @{ S = $ProductId }

    recipients = @{ L = $recipientList }

    created_at = @{ S = $createdAtIso }
	
	include_tags = @{
		L = @(
			@{ S = "Member" },
			@{ S = "VIP" }
		)
	}
	
	next_run_time = @{ S = $nextRunIso }
}


# ===== save =====
$dir = Split-Path -Parent $OutputFile
if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }

$campaign | ConvertTo-Json -Depth 50 | Out-File -Encoding utf8 $OutputFile

Write-Host "Generated: $OutputFile"
Write-Host "pk: $pk"
Write-Host "recipients: $($phonesNorm.Count)"
Write-Host "next_run_format: $NextRunFormat"
