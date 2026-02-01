Param(
    [string]$ApiUrl = "",
    [string]$StackName = "botman-dev"
)

Write-Host "=== Botman AI - manual_test_pg.ps1 ==="

# Jezeli ApiUrl nie jest podany, probujemy pobrac go ze stacka (AWS)
if ($ApiUrl -eq "") {

    Write-Host "ApiUrl not provided. Reading PgTestUrl from CloudFormation stack:"
    Write-Host "  StackName: $StackName"

    $ApiUrl = aws cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='PgTestUrl'].OutputValue" --output text

    if ($ApiUrl -eq "" -or $ApiUrl -eq "None") {
        Write-Host "ERROR: PgTestUrl could not be resolved from stack."
        Write-Host "Provide ApiUrl manually using -ApiUrl parameter (for local/ngrok testing)."
        exit 1
    }

    Write-Host "Resolved ApiUrl (PgTestUrl) from AWS:"
    Write-Host "  $ApiUrl"
} else {
    Write-Host "Using ApiUrl passed as parameter:"
    Write-Host "  $ApiUrl"
}

# Body requestu PG
$BodyObject = @{
    member_id       = "112"
    class_id        = "777"
    idempotency_key = "test-conv-1#msg-1#reserve"
}

$Body = $BodyObject | ConvertTo-Json

Write-Host ""
Write-Host "=== Sending POST ==="
Write-Host "URL:"
Write-Host "  $ApiUrl"
Write-Host "Body:"
Write-Host "  $Body"
Write-Host ""

$response = Invoke-WebRequest -Uri $ApiUrl -Method POST -ContentType "application/json" -Body $Body

Write-Host ""
Write-Host "=== Response ==="
Write-Host "StatusCode:"
Write-Host "  $($response.StatusCode)"
Write-Host "Content:"
Write-Host $response.Content
