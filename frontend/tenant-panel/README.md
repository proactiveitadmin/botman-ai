# Botman AI — Tenant Frontend Panel

Frontend demo dla osobnego panelu per tenant.

## Funkcje

- logowanie email + hasło przez AWS Cognito,
- obsługa pierwszego logowania z hasłem tymczasowym i ustawieniem hasła stałego,
- panel powitalny po zalogowaniu,
- tworzenie kampanii: treść wiadomości, lista numerów, data i godzina wysyłki,
- statystyki miesięczne z prostym wykresem.

## Konfiguracja

Skopiuj `.env.example` do `.env`:

```powershell
Copy-Item .env.example .env
```

Ustaw:

```env
VITE_API_BASE_URL= https://xxxxxxxxxx.execute-api.eu-central-1.amazonaws.com/Prod
VITE_TENANT_ID=clubProactiveIT
VITE_COGNITO_USER_POOL_ID=eu-central-xxxxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
```

`TenantUserPoolId` i `TenantUserPoolClientId` są w outputach stacka SAM/CloudFormation.
 - AWS CloudFormation
 - wybierz stack
 - zakładka Outputs
 lub dla stage:
 aws cloudformation describe-stacks `
  --stack-name botman-stage `
  --query "Stacks[0].Outputs" `
  --output table
## Utworzenie użytkownika Cognito

Po deployu utwórz użytkownika w Cognito i ustaw atrybut `custom:tenant_id` zgodny z `VITE_TENANT_ID`:

```powershell
aws cognito-idp admin-create-user `
  --user-pool-id eu-central-xxxxxxxxxxx `
  --username admin@example.com `
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true Name=custom:tenant_id,Value=clubProactiveIT`
  --temporary-password "xxx111!" `
  --region eu-central-1
```

Przy pierwszym logowaniu frontend pokaże pole na nowe hasło stałe.

## Uruchomienie

```powershell
npm install
npm run dev
```

## Build

```powershell
npm run build
npm run preview
```
