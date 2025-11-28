# ==== KONFIGURACJA ====
$tableName = "Templates-botman-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
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
  
# ==== 6. pg_available_classes_empty ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_empty"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Aktualnie nie widzę dostępnych zajęć w grafiku."},
    "placeholders":  {"L": []}
  }'
  
# ==== 7. pg_available_classes_capacity_no_limit ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_no_limit"},
    "language_code": {"S": "pl"},
    "body":          {"S": "bez limitu miejsc"},
    "placeholders":  {"L": []}
  }'
  
# ==== 8. pg_available_classes_capacity_full ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_full"},
    "language_code": {"S": "pl"},
    "body":          {"S": "brak wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": []}
  }'
  
# ==== 9. pg_available_classes_capacity_free ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_free"},
    "language_code": {"S": "pl"},
    "body":          {"S": "{free} wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": []}
  }'
  
# ==== 10. pg_available_classes_item ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_item"},
    "language_code": {"S": "pl"},
    "body":          {"S": "{date} {time} – {name} ({capacity})"},
    "placeholders":  {"L": []}
  }'
  
# ==== 11. pg_available_classes ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Najbliższe zajęcia:\n{classes}"},
    "placeholders":  {"L": []}
  }'  
  
# ==== 12. pg_contract_ask_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_contract_ask_email"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Podaj proszę adres e-mail użyty w klubie, żebym mógł sprawdzić status Twojej umowy."},
    "placeholders":  {"L": []}
  }'  
  
# ==== 13. pg_contract_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie widzę żadnej umowy powiązanej z adresem {email} i numerem {phone}. Upewnij się proszę, że dane są zgodne z PerfectGym."},
    "placeholders":  {"L": []}
  }'  
  
# ==== 14. pg_contract_details ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Szczegóły Twojej umowy:\nPlan: {plan_name}\nStatus:\n{status}\nAktywna: {is_active, select, true{tak} false{nie}}\nStart: {start_date}\nKoniec: {end_date}\nOpłata członkowska: {membership_fee}"},
    "placeholders":  {"L": []}
  }'

  
# ==== 15. reserve_class_confirmed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirmed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Zarezerwowano zajęcia (ID {class_id}). Do zobaczenia!"},
    "placeholders":  {"L": []}
  }'
    
# ==== 16. reserve_class_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_failed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie udało się zarezerwować. Spróbuj ponownie później."},
    "placeholders":  {"L": []}
  }'
    
# ==== 17. reserve_class_confirmed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_declined"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Anulowano rezerwację. Daj znać, jeżeli będziesz chciał/chciała zarezerwować inne zajęcia."},
    "placeholders":  {"L": []}
  }'    
  
# ==== 18. www_not_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_not_verified"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie znaleziono aktywnej weryfikacji dla tego kodu."},
    "placeholders":  {"L": []}
  }'
# ==== 19. www_user_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_user_not_found"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie znaleziono członkostwa powiązanego z tym numerem."},
    "placeholders":  {"L": []}
  }'
# ==== 20. www_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_verified"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Twoje konto zostało zweryfikowane. Możesz wrócić do czatu WWW."},
    "placeholders":  {"L": []}
  }'
  
# ==== 21. pg_web_verification_required ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_web_verification_required"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Aby kontynuować, musimy potwierdzić Twoją tożsamość.\n\nJeśli korzystasz z czatu WWW, kliknij poniższy link, aby otworzyć WhatsApp i wysłać kod weryfikacyjny.\nJeśli jesteś już w WhatsApp, wystarczy że wyślesz poniższy kod.\n\nKod: {{verification_code}}\nLink: {{whatsapp_link}}\n\nPo wysłaniu kodu wróć do rozmowy – zweryfikujemy Twoje konto i odblokujemy dostęp do danych PerfectGym."},
        "placeholders":  {"L": [
      { "S": "verification_code" },
      { "S": "whatsapp_link" }
    ]}
  }'
  # ==== 22. faq_no_info ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "faq_no_info"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Przepraszam, nie mam informacji."},
    "placeholders":  {"L": []}
  }'
  # ==== 23. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy potwierdzasz rezerwację zajęć {class_id}? Odpowiedz: TAK lub NIE."},
    "placeholders":  {"L": []}
  }'
  # ==== 24. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm_words"},
    "language_code": {"S": "pl"},
    "body":          {"S": "tak, tak., potwierdzam, ok, zgadzam się, oczywiście, pewnie, jasne"},
    "placeholders":  {"L": []}
  }'
  # ==== 25. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_decline_words"},
    "language_code": {"S": "pl"},
    "body":          {"S": "nie, nie., anuluj, rezygnuję, rezygnuje"},
    "placeholders":  {"L": []}
  }'

