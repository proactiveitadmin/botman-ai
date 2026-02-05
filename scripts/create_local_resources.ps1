<# create_local_resources.ps1 (SQS only) #>

[CmdletBinding()]
param(
  [string]$Endpoint  = "http://localhost:4566",
  [string]$Region    = "eu-central-1",
  [string]$StackName = "botman-dev"
)

$ErrorActionPreference = "Stop"

Write-Host "Endpoint: $Endpoint"
Write-Host "Region:   $Region"
Write-Host "Stack:    $StackName"
Write-Host ""

function Get-QueueUrl([string]$QueueName) {
  $json = & aws --no-cli-pager --endpoint-url $Endpoint --region $Region sqs get-queue-url --queue-name $QueueName
  return ($json | ConvertFrom-Json).QueueUrl
}

function Get-QueueArn([string]$QueueUrl) {
  $json = & aws --no-cli-pager --endpoint-url $Endpoint --region $Region sqs get-queue-attributes `
    --queue-url $QueueUrl --attribute-names QueueArn
  return (($json | ConvertFrom-Json).Attributes).QueueArn
}

function Ensure-Queue([string]$QueueName, [string[]]$Attributes) {
  try {
    $existing = & aws --no-cli-pager --endpoint-url $Endpoint --region $Region sqs get-queue-url --queue-name $QueueName 2>$null
    if ($LASTEXITCODE -eq 0 -and $existing) {
      Write-Host "SQS exists: $QueueName"
      return ($existing | ConvertFrom-Json).QueueUrl
    }
  } catch {}

  if ($null -ne $Attributes -and $Attributes.Count -gt 0) {
    & aws --no-cli-pager --endpoint-url $Endpoint --region $Region sqs create-queue `
      --queue-name $QueueName `
      --attributes $Attributes | Out-Null
  } else {
    & aws --no-cli-pager --endpoint-url $Endpoint --region $Region sqs create-queue `
      --queue-name $QueueName | Out-Null
  }

  Write-Host "SQS created: $QueueName"
  return Get-QueueUrl $QueueName
}

Write-Host "=== Creating SQS queues ==="

# Names (match template.yaml intent)
$inboundName     = "inbound-events-$StackName.fifo"
$inboundDlqName  = "inbound-events-$StackName-dlq.fifo"
$outboundName    = "outbound-messages-$StackName"
$outboundDlqName = "outbound-messages-$StackName-dlq"

# 1) DLQs
$inboundDlqUrl = Ensure-Queue $inboundDlqName @(
  "FifoQueue=true"
  "ContentBasedDeduplication=false"
)

$outboundDlqUrl = Ensure-Queue $outboundDlqName @()

# 2) ARNs
$inboundDlqArn  = Get-QueueArn $inboundDlqUrl
$outboundDlqArn = Get-QueueArn $outboundDlqUrl

# 3) RedrivePolicy JSON
$inboundRedrive  = @{ deadLetterTargetArn = $inboundDlqArn;  maxReceiveCount = 5 } | ConvertTo-Json -Compress
$outboundRedrive = @{ deadLetterTargetArn = $outboundDlqArn; maxReceiveCount = 5 } | ConvertTo-Json -Compress

# 4) Main queues
$inboundUrl = Ensure-Queue $inboundName @(
  "FifoQueue=true"
  "ContentBasedDeduplication=false"
  "VisibilityTimeout=60"
  "RedrivePolicy=$inboundRedrive"
)

$outboundUrl = Ensure-Queue $outboundName @(
  "VisibilityTimeout=60"
  "RedrivePolicy=$outboundRedrive"
)

# 5) Export ENV for this PS session
$Env:InboundEventsQueueUrl = $inboundUrl
$Env:OutboundQueueUrl      = $outboundUrl

Write-Host ""
Write-Host "InboundEventsQueueUrl = $Env:InboundEventsQueueUrl"
Write-Host "OutboundQueueUrl      = $Env:OutboundQueueUrl"
Write-Host ""
Write-Host "Done."
