Param(
    [string]$Endpoint="http://localhost:4566",
    [string]$Region="eu-central-1"
)

#"=== Botman AI – create_local_resources.ps1 ==="
Write-Host Endpoint: $Endpoint
Write-Host Region: $Region
Write-Host

#"=== SQS queues ==="

aws --endpoint-url $Endpoint --region $Region sqs create-queue --queue-name inbound-events
aws --endpoint-url $Endpoint --region $Region sqs create-queue --queue-name inbound-events-dlq
aws --endpoint-url $Endpoint --region $Region sqs create-queue --queue-name outbound-messages
aws --endpoint-url $Endpoint --region $Region sqs create-queue --queue-name outbound-messages-dlq

#"=== DynamoDB tables ==="

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Tenants --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=tenant_id,AttributeType=S --key-schema AttributeName=tenant_id,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Conversations --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Messages --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Templates --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Campaigns --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Consents --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name IntentsStats --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name MembersIndex --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

aws --endpoint-url $Endpoint --region $Region dynamodb create-table --table-name Consents --billing-mode PAY_PER_REQUEST --attribute-definitions AttributeName=pk,AttributeType=S --key-schema AttributeName=pk,KeyType=HASH

#"=== S3 bucket ==="

aws --endpoint-url $Endpoint --region $Region s3api create-bucket --bucket local-kb
