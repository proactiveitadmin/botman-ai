# ==== KONFIGURACJA ====
$tableName = "Templates-botman-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"              # <- jeśli używasz innego, zmień

# ==== 1. handover_to_staff ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#handover_to_staff#pl"},
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
    "pk":            {"S": "default#ticket_summary#pl"},
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
    "pk":            {"S": "default#ticket_created_ok#pl"},
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
    "pk":            {"S": "default#ticket_created_failed#pl"},
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
    "pk":            {"S": "default#clarify_generic#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "clarify_generic"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy możesz doprecyzować, w czym pomóc?"},
    "placeholders":  {"L": []}
  }'

# =========================
#      PERFECTGYM – LISTA ZAJĘĆ
# =========================

# ==== 6. pg_available_classes ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dostępne zajęcia:\n{classes}\n\nNapisz numer wybranych zajęć (np. 1)."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 7. pg_available_classes_empty ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_empty#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_empty"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Aktualnie nie widzę dostępnych zajęć w grafiku."},
    "placeholders":  {"L": []}
  }'

# ==== 8. pg_available_classes_capacity_no_limit ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_capacity_no_limit#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_no_limit"},
    "language_code": {"S": "pl"},
    "body":          {"S": "bez limitu miejsc"},
    "placeholders":  {"L": []}
  }'

# ==== 9. pg_available_classes_capacity_full ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_capacity_full#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_full"},
    "language_code": {"S": "pl"},
    "body":          {"S": "brak wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": [ { "S": "limit" } ]}
  }'

# ==== 10. pg_available_classes_capacity_free ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_capacity_free#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_capacity_free"},
    "language_code": {"S": "pl"},
    "body":          {"S": "{free} wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": [ { "S": "free" }, { "S": "limit" } ]}
  }'

# ==== 11. pg_available_classes_item ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_item#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_item"},
    "language_code": {"S": "pl"},
    "body":          {"S": "{index}) {date} {time} – {name} {capacity}"},
    "placeholders":  {
      "L": [
        { "S": "index" },
        { "S": "date" },
        { "S": "time" },
        { "S": "name" },
        { "S": "capacity" }
      ]
    }
  }'

# ==== 12. pg_available_classes_invalid_index ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_invalid_index#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_invalid_index"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie rozumiem wyboru. Podaj numer zajęć od 1 do {max_index}."},
    "placeholders":  {"L": [ { "S": "max_index" } ]}
  }'

# ==== 13. pg_available_classes_no_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_no_today#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_no_today"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dzisiaj nie mamy żadnych dostępnych zajęć."},
    "placeholders":  {"L": []}
  }'

# ==== 14. pg_available_classes_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_today#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_today"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dzisiaj mamy takie zajęcia:\n{classes}\n\nNapisz numer wybranych zajęć."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 15. pg_available_classes_no_classes_on_date ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_no_classes_on_date#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_no_classes_on_date"},
    "language_code": {"S": "pl"},
    "body":          {"S": "W dniu {date} nie mamy żadnych dostępnych zajęć."},
    "placeholders":  {"L": [ { "S": "date" } ]}
  }'

# ==== 16. pg_available_classes_select_by_number ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_available_classes_select_by_number#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_available_classes_select_by_number"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Tego dnia są różne zajęcia. Napisz numer zajęć, które chcesz zarezerwować."},
    "placeholders":  {"L": []}
  }'

# =========================
#      PERFECTGYM – KONTRAKT / WERYFIKACJA
# =========================

# ==== 17. pg_contract_ask_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_contract_ask_email#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_contract_ask_email"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Podaj proszę adres e-mail użyty w klubie, żebym mógł sprawdzić status Twojej umowy."},
    "placeholders":  {"L": []}
  }'

# ==== 18. pg_contract_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_contract_not_found#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_contract_not_found"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie widzę żadnej umowy powiązanej z adresem {email} i numerem {phone}. Upewnij się proszę, że dane są zgodne z PerfectGym."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 19. pg_contract_details ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_contract_details#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_contract_details"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Szczegóły Twojej umowy:\nPlan: {plan_name}\nStatus: {status}\nAktywna: {is_active}\nStart: {start_date}\nKoniec: {end_date}\nOpłata członkowska: {membership_fee}"},
    "placeholders":  {
      "L": [
        { "S": "plan_name" },
        { "S": "status" },
        { "S": "is_active" },
        { "S": "start_date" },
        { "S": "end_date" },
        { "S": "membership_fee" }
      ]
    }
  }'

# =========================
#      REZERWACJE ZAJĘĆ
# =========================

# ==== 20. reserve_class_confirmed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirmed#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirmed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Zarezerwowano zajęcia (ID {class_id}). Do zobaczenia!"},
    "placeholders":  {"L": [ { "S": "class_id" } ]}
  }'

# ==== 21. reserve_class_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_failed#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_failed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie udało się zarezerwować. Spróbuj ponownie później."},
    "placeholders":  {"L": []}
  }'

# ==== 22. reserve_class_declined ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_declined#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_declined"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Anulowano rezerwację. Daj znać, jeżeli będziesz chciał/chciała zarezerwować inne zajęcia."},
    "placeholders":  {"L": []}
  }'

# ==== 23. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy potwierdzasz rezerwację zajęć {class_id}? Odpowiedz: TAK lub NIE."},
    "placeholders":  {"L": [ { "S": "class_id" } ]}
  }'

# ==== 24. reserve_class_missing_id ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_missing_id#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_missing_id"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie udało się zidentyfikować zajęć do rezerwacji. Spróbuj jeszcze raz."},
    "placeholders":  {"L": []}
  }'

# ==== 25. reserve_class_confirm_words (lista słów TAK) ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm_words#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm_words"},
    "language_code": {"S": "pl"},
    "body":          {"S": "tak,tak.,potwierdzam,ok,zgadzam się,zgadzam sie,oczywiście,oczywiscie,pewnie,jasne"},
    "placeholders":  {"L": []}
  }'

# ==== 26. reserve_class_decline_words (lista słów NIE) ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_decline_words#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_decline_words"},
    "language_code": {"S": "pl"},
    "body":          {"S": "nie,nie.,anuluj,rezygnuję,rezygnuje,nie chcę,nie chce"},
    "placeholders":  {"L": []}
  }'

# =========================
#      WERYFIKACJA WWW / FAQ
# =========================

# ==== 27. www_not_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_not_verified#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_not_verified"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie znaleziono aktywnej weryfikacji dla tego kodu."},
    "placeholders":  {"L": []}
  }'

# ==== 28. www_user_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_user_not_found#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_user_not_found"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie znaleziono członkostwa powiązanego z tym numerem."},
    "placeholders":  {"L": []}
  }'

# ==== 29. www_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_verified#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_verified"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Twoje konto zostało zweryfikowane. Możesz wrócić do czatu WWW."},
    "placeholders":  {"L": []}
  }'

# ==== 30. pg_web_verification_required ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#pg_web_verification_required#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "pg_web_verification_required"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Aby kontynuować, musimy potwierdzić Twoją tożsamość.\n\nJeśli korzystasz z czatu WWW, kliknij poniższy link, aby otworzyć WhatsApp i wysłać kod weryfikacyjny.\nJeśli jesteś już w WhatsApp, wystarczy że wyślesz poniższy kod.\n\nKod: {{verification_code}}\nLink: {{whatsapp_link}}\n\nPo wysłaniu kodu wróć do rozmowy – zweryfikujemy Twoje konto i odblokujemy dostęp do danych PerfectGym."},
    "placeholders":  {
      "L": [
        { "S": "verification_code" },
        { "S": "whatsapp_link" }
      ]
    }
  }'

# ==== 31. faq_no_info ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#faq_no_info#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "faq_no_info"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Przepraszam, nie mam informacji."},
    "placeholders":  {"L": []}
  }'

# =========================
#      POWITANIE
# =========================

# ==== 32. greeting ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#greeting#pl"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "greeting"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Cześć! Jestem wirtualnym asystentem klubu fitness. Napisz, w czym mogę pomóc."},
    "placeholders":  {"L": []}
  }'
