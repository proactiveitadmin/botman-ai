# ==== KONFIGURACJA ====
$tableName = "Templates-gi-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"          # <- jeśli używasz innego, zmień

# ==== 1. handover_to_staff ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "handover_to_staff"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Łączę Cię z pracownikiem klubu (wkrótce stałe przełączenie)."},
    "placeholders":  {"L": []}
  }'

# ==== 2. ticket_summary ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_summary"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Zgłoszenie klienta"},
    "placeholders":  {"L": []}
  }'

# ==== 3. ticket_created_ok ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_ok"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Utworzyłem zgłoszenie. Numer: %{ticket}."},
    "placeholders":  {"L": [ { "S": "ticket" } ]}
  }'

# ==== 4. ticket_created_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_failed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie udało się utworzyć zgłoszenia. Spróbuj później."},
    "placeholders":  {"L": []}
  }'

# ==== 5. clarify_generic ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "clarify_generic"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy możesz doprecyzować, w czym pomóc?"},
    "placeholders":  {"L": []}
  }'
