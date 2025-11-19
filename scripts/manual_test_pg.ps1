#api URL do pg:
$apiUrl = aws cloudformation describe-stacks `
  --stack-name gi-dev `
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" `
  --output text

$Body = @{
    member_id       = "112"
    class_id        = "777"
    idempotency_key = "test-conv-1#msg-1#reserve"
} | ConvertTo-Json

Invoke-WebRequest `
    -Uri $apiUrl `
    -Method POST `
    -ContentType "application/json" `
    -Body $Body
