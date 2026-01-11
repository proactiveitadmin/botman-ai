# ==== KONFIGURACJA ====
$tableName = "Templates-botman-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"              # <- jeśli używasz innego, zmień

# ==== 1. handover_to_staff ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#handover_to_staff#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#ticket_summary#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#ticket_created_ok#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#ticket_created_failed#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#clarify_generic#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "clarify_generic"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy możesz doprecyzować, w czym pomóc?"},
    "placeholders":  {"L": []}
  }'

# =========================
#      PERFECTGYM – LISTA ZAJĘĆ
# =========================

# ==== 6. crm_available_classes ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dostępne zajęcia:\n\n{classes}\n"},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 7. crm_available_classes_empty ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_empty#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_empty"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Aktualnie nie widzę dostępnych zajęć w grafiku."},
    "placeholders":  {"L": []}
  }'

# ==== 8. crm_available_classes_capacity_no_limit ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_capacity_no_limit#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_capacity_no_limit"},
    "language_code": {"S": "pl"},
    "body":          {"S": "bez limitu miejsc"},
    "placeholders":  {"L": []}
  }'

# ==== 9. crm_available_classes_capacity_full ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_capacity_full#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_capacity_full"},
    "language_code": {"S": "pl"},
    "body":          {"S": "brak wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": [ { "S": "limit" } ]}
  }'

# ==== 10. crm_available_classes_capacity_free ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_capacity_free#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_capacity_free"},
    "language_code": {"S": "pl"},
    "body":          {"S": "*{free}* wolnych miejsc (limit {limit})"},
    "placeholders":  {"L": [ { "S": "free" }, { "S": "limit" } ]}
  }'

# ==== 11. crm_available_classes_item ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_item#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_item"},
    "language_code": {"S": "pl"},
    "body":          {"S": "{index}) *{date}* {time} – {name} {capacity}"},
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

# ==== 12. crm_available_classes_invalid_index ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_invalid_index#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_invalid_index"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie rozumiem wyboru. Podaj numer zajęć od 1 do {max_index}."},
    "placeholders":  {"L": [ { "S": "max_index" } ]}
  }'

# ==== 13. crm_available_classes_no_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_no_today#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_no_today"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dzisiaj nie mamy żadnych dostępnych zajęć."},
    "placeholders":  {"L": []}
  }'

# ==== 14. crm_available_classes_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_today#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_today"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Dzisiaj mamy takie zajęcia:\n{classes}\n"},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 15. crm_available_classes_no_classes_on_date ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_no_classes_on_date#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_no_classes_on_date"},
    "language_code": {"S": "pl"},
    "body":          {"S": "W dniu {date} nie mamy żadnych dostępnych zajęć."},
    "placeholders":  {"L": [ { "S": "date" } ]}
  }'

# ==== 16. crm_available_classes_select_by_number ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_available_classes_select_by_number#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_available_classes_select_by_number"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Tego dnia są różne zajęcia. Napisz numer zajęć, które chcesz zarezerwować(np 1)."},
    "placeholders":  {"L": []}
  }'

# =========================
#      PERFECTGYM – KONTRAKT / WERYFIKACJA
# =========================

# ==== 17. crm_contract_ask_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_contract_ask_email#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_contract_ask_email"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Podaj proszę adres e-mail użyty w klubie, żebym mógł sprawdzić status Twojej umowy."},
    "placeholders":  {"L": []}
  }'

# ==== 18. crm_contract_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_contract_not_found#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_contract_not_found"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Nie widzę żadnej umowy powiązanej z adresem {email} i numerem {phone}. Upewnij się proszę, że dane są zgodne z PerfectGym."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'
  
# ==== 18.a crm_challenge_ask_dob ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_ask_dob#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_ask_dob"},
    "language_code": {"S": "pl"},
    "body":          {"S": "W celu weryfikacji podaj swoją datę urodzenia(weryfikacja tymczasowa)."},
    "placeholders":  {"L": []}
  }'
  
# ==== 18.b crm_challenge_success ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_success#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_success"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Zweryfikowaliśmy Twoje konto."},
    "placeholders":  {"L": []}
  }'
# ==== 19. crm_contract_details ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_contract_details#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_contract_details"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Szczegóły Twojej umowy:\nPlan: {plan_name}\nStatus: {status}\nStart: {start_date}\nKoniec: {end_date}\nBieżące saldo: {current_balance}\nZadłużenie od: {negative_balance_since}"},
    "placeholders":  {
      "L": [
        { "S": "plan_name" },
        { "S": "plan_name" },
        { "S": "status" },
        { "S": "start_date" },
        { "S": "end_date" },
        { "S": "current_balance" },
        { "S": "negative_balance_since" }
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
    "pk":            {"S": "clubProactiveIT#reserve_class_confirmed#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "reserve_class_confirmed"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Zarezerwowano {class_name} w dniu {class_date} o {class_time}. Do zobaczenia!"},
    "placeholders":  {"L": [ 
		{ "S": "class_name" },
        { "S": "class_date" },
        { "S": "class_time" } 
	  ]
	}
  }'

# ==== 21. reserve_class_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#reserve_class_failed#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#reserve_class_declined#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "reserve_class_declined"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Rezerwacja odrzucona. Daj znać, jeżeli będziesz chciał/chciała zarezerwować inne zajęcia."},
    "placeholders":  {"L": []}
  }'

# ==== 23. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#reserve_class_confirm#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "reserve_class_confirm"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Czy potwierdzasz rezerwację zajęć {class_name}, {class_date} o godzinie {class_time}? Odpowiedz: TAK lub NIE."},
    "placeholders":  {"L": [ { "S": "class_name" },
							 { "S": "class_date" },
							 { "S": "class_time" }
						]}
  }'

# ==== 24. reserve_class_missing_id ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#reserve_class_missing_id#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#reserve_class_confirm_words#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#reserve_class_decline_words#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#www_not_verified#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#www_user_not_found#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
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
    "pk":            {"S": "clubProactiveIT#www_verified#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "www_verified"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Twoje konto zostało zweryfikowane. Możesz wrócić do czatu WWW."},
    "placeholders":  {"L": []}
  }'

# ==== 30. crm_web_verification_required ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_web_verification_required#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_web_verification_required"},
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
    "pk":            {"S": "clubProactiveIT#faq_no_info#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "faq_no_info"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Przepraszam, nie mam informacji. . Czy mogę jeszcze w czymś pomóc?"},
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
    "pk":            {"S": "clubProactiveIT#greeting#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "greeting"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Cześć! Jestem wirtualnym asystentem klubu fitness. Napisz, w czym mogę pomóc."},
    "placeholders":  {"L": []}
  }'
# ==== 33. crm_challenge_retry ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_retry#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_retry"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Weryfikacja nie powiodła się. Sprobuj jeszcze raz"},
    "placeholders":  {"L": []}
  }'
# ==== 34. crm_challenge_fail_handover ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_fail_handover#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_fail_handover"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Weryfikacja zostala tymczasowo zablokowana. Sprobuj jeszcze raz za 15 minut lub skontaktuj sie z obsługą klienta."},
    "placeholders":  {"L": []}
  }'

# ==== CRM: crm_challenge_ask_email_code ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_ask_email_code#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_ask_email_code"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Wysłaliśmy kod weryfikacyjny na adres {{email}}. Wpisz go tutaj, aby kontynuować."},
    "placeholders":  {"L": [{"S": "email"}]}
  }'

# ==== CRM: crm_code_via_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_code_via_email#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_code_via_email"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Twój kod weryfikacyjny to: {{verification_code}}\n\nKod jest ważny przez {{ttl_minutes}} minut.\n\nJeśli to nie Ty inicjowałeś weryfikację, zignoruj tę wiadomość."},
    "placeholders":  {"L": [{"S": "verification_code"}, {"S": "ttl_minutes"}]}
  }'

# ==== CRM: crm_challenge_expired ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "clubProactiveIT#crm_challenge_expired#pl"},
    "tenant_id":     {"S": "clubProactiveIT"},
    "template_code": {"S": "crm_challenge_expired"},
    "language_code": {"S": "pl"},
    "body":          {"S": "Weryfikacja wygasła. Poproś o nowy kod, aby kontynuować."},
    "placeholders":  {"L": []}
  }'

