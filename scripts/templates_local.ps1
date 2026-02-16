# ==== KONFIGURACJA ====
$tableName = "Templates-botman-dev"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"              # <- jeśli używasz innego, zmień
# ==== 1. handover_to_staff ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#handover_to_staff#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "handover_to_staff"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Już przekazuję Twoją sprawę do recepcji. Jeśli to pilne, możesz też podejść do stanowiska obsługi lub zadzwonić do klubu."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 2. ticket_summary ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_summary#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_summary"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Zgłoszenie do recepcji"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 2.1. ticket_description ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_description#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_description"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Zgłoszenie z chatu.\nOstatnia wiadomość:\n{body}\nHistoria:\n{history_block}"
    },
    "placeholders": {
        "L": [
            {
                "S": "body"
            },
            {
                "S": "history_block"
            }
		]
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item

# ==== 3. ticket_created_ok ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_created_ok#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_ok"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Dziękuję — zgłoszenie zostało utworzone. Numer sprawy: *{ticket}*. Wrócimy do Ciebie, gdy tylko je sprawdzimy."
    },
    "placeholders": {
        "L": [
            {
                "S": "ticket"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 4. ticket_created_failed ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_created_failed#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_failed"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie udało się utworzyć zgłoszenia. Spróbuj proszę ponownie za chwilę — a jeśli problem się powtórzy, napisz co się dzieje, a przekażę to do recepcji."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 5. clarify_generic ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#clarify_generic#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "clarify_generic"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Jasne — doprecyzujesz proszę, czego dotyczy sprawa? (np. karnet, płatność, zajęcia, rezerwacja, aplikacja)"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 6. crm_available_classes ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Oto dostępne zajęcia w grafiku:\n\n{classes}\n"
    },
    "placeholders": {
        "L": [
            {
                "S": "classes"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 7. crm_available_classes_empty ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_empty#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_empty"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Na ten moment nie widzę dostępnych zajęć w grafiku. Spróbuj proszę później albo podaj preferowany dzień i godzinę — sprawdzę alternatywy."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 8. crm_available_classes_capacity_no_limit ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_no_limit#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_no_limit"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "bez limitu miejsc"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 9. crm_available_classes_capacity_full ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_full#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_full"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "brak wolnych miejsc (limit {limit})"
    },
    "placeholders": {
        "L": [
            {
                "S": "limit"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 10. crm_available_classes_capacity_free ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_free#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_free"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "*{free}* wolnych miejsc (limit {limit})"
    },
    "placeholders": {
        "L": [
            {
                "S": "free"
            },
            {
                "S": "limit"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 11. crm_available_classes_item ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_item#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_item"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "{index}) *{date}* {time} – {name} {capacity}"
    },
    "placeholders": {
        "L": [
            {
                "S": "index"
            },
            {
                "S": "date"
            },
            {
                "S": "time"
            },
            {
                "S": "name"
            },
            {
                "S": "capacity"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 12. crm_available_classes_invalid_index ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_invalid_index#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_invalid_index"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie mogę dopasować wyboru. Podaj proszę numer zajęć od 1 do {max_index}."
    },
    "placeholders": {
        "L": [
            {
                "S": "max_index"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 13. crm_available_classes_no_today ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_no_today#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_today"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Dzisiaj nie widzę żadnych dostępnych zajęć. Jeśli chcesz, sprawdzę inny dzień — podaj datę."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 14. crm_available_classes_today ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_today#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_today"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Dzisiaj dostępne są:\n\n{classes}\n\nWybierz numer z listy, a pomogę z rezerwacją."
    },
    "placeholders": {
        "L": [
            {
                "S": "classes"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 15. crm_available_classes_no_classes_on_date ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_no_classes_on_date#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_classes_on_date"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "W dniu *{date}* nie widzę dostępnych zajęć. Jeśli chcesz, mogę sprawdzić najbliższe terminy — podaj preferowany dzień tygodnia lub godzinę."
    },
    "placeholders": {
        "L": [
            {
                "S": "date"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 16. crm_available_classes_select_by_number ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_select_by_number#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_select_by_number"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Wybierz proszę numer zajęć z listy (np. 1, 2, 3)."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 17. crm_contract_not_found ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_contract_not_found#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_not_found"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie widzę aktywnego konta dla podanych danych.\n\nSprawdź proszę, czy e‑mail (*{email}*) lub telefon (*{phone}*) są takie same jak przy zapisie do klubu. Jeśli nadal nie działa, mogę przekazać sprawę do recepcji."
    },
    "placeholders": {
        "L": [
            {
                "S": "email"
            },
            {
                "S": "phone"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 18. crm_challenge_success ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_success#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_success"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Dziękuję — weryfikacja zakończona pomyślnie. Możemy kontynuować."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 19. crm_contract_details ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_contract_details#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_details"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Oto szczegóły Twojego członkostwa:\n\n• Plan: *{plan_name}*\n• Status: *{status}*\n• Od: *{start_date}*\n• Do: *{end_date}*\n• Saldo: *{current_balance}*\n• Ujemne saldo od: *{negative_balance_since}*\n\nJeśli coś się nie zgadza, daj znać — pomogę wyjaśnić to z recepcją."
    },
    "placeholders": {
        "L": [
            {
                "S": "plan_name"
            },
            {
                "S": "plan_name"
            },
            {
                "S": "status"
            },
            {
                "S": "start_date"
            },
            {
                "S": "end_date"
            },
            {
                "S": "current_balance"
            },
            {
                "S": "negative_balance_since"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 20. crm_member_not_linked ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_member_not_linked#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_not_linked"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie mogę jeszcze powiązać tego czatu z Twoim kontem w klubie. Jeśli chcesz korzystać z danych (np. karnet, płatności, rezerwacje), przejdź proszę weryfikację lub skontaktuj się z recepcją."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 21. crm_member_balance ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_member_balance#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_balance"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Twoje aktualne saldo wynosi: *{balance}*.\n\nJeśli masz pytania o rozliczenia, mogę też podpowiedzieć, skąd wynika ta kwota."
    },
    "placeholders": {
        "L": [
            {
                "S": "balance"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 22. reserve_class_confirmed ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_confirmed#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirmed"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Super — rezerwacja została potwierdzona ✅\n\n*{class_name}* — {class_date} o {class_time}\n\nJeśli chcesz odwołać lub zmienić termin, napisz — pomogę."
    },
    "placeholders": {
        "L": [
            {
                "S": "class_name"
            },
            {
                "S": "class_date"
            },
            {
                "S": "class_time"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 23. reserve_class_already_booked ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_already_booked#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_already_booked"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Widzę, że jesteś już zapisany/a na te zajęcia.\n\n*{class_name}* — {class_date} o {class_time}\n\nJeśli chcesz, mogę sprawdzić inne terminy lub dostępne miejsca na podobnych zajęciach."
    },
    "placeholders": {
        "L": [
            {
                "S": "class_id"
            },
            {
                "S": "class_name"
            },
            {
                "S": "class_date"
            },
            {
                "S": "class_time"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 24. reserve_class_failed ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_failed#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_failed"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie udało się zarezerwować zajęć. Spróbuj proszę ponownie za chwilę — a jeśli błąd wróci, podaj nazwę zajęć i datę, a przekażę sprawę do recepcji."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 25. reserve_class_declined ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_declined#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_declined"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Okej, nie robię rezerwacji. Jeśli zmienisz zdanie, podaj numer zajęć z listy — wrócimy do tego."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 26. reserve_class_confirm ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_confirm#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirm"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Czy na pewno chcesz zarezerwować:\n\n*{class_name}* — {class_date} o {class_time}?\n\nOdpowiedz: *tak* / *nie*."
    },
    "placeholders": {
        "L": [
            {
                "S": "class_name"
            },
            {
                "S": "class_date"
            },
            {
                "S": "class_time"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 27. reserve_class_missing_id ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_missing_id#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_missing_id"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie widzę identyfikatora zajęć, więc nie mogę dokończyć rezerwacji. Wybierz proszę zajęcia z listy (numer), a spróbujemy ponownie."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 28. www_not_verified ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_not_verified#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_not_verified"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Aby wyświetlić dane z PerfectGym, potrzebuję krótkiej weryfikacji. Poproś o kod i wpisz go tutaj — zajmie to chwilę."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 29. www_user_not_found ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_user_not_found#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_user_not_found"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie mogę znaleźć konta powiązanego z tym czatem. Sprawdź proszę dane użyte przy zapisie do klubu lub skontaktuj się z recepcją, aby zaktualizować profil."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 30. www_verified ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_verified#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_verified"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Dziękuję — konto zostało zweryfikowane. Możemy przejść dalej 😊"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#web_crm_not_available#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "web_crm_not_available"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "This feature is available only for Whatsapp channel. Please use your whatsapp to continue."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 32. faq_no_info ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#faq_no_info#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "faq_no_info"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie widzę tej informacji w FAQ. Jeśli chcesz, mogę przekazać pytanie do recepcji albo podpowiedzieć, gdzie to sprawdzić (np. w aplikacji)."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 33. crm_challenge_retry ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_retry#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_retry"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Kod nie zadziałał. Spróbuj proszę wpisać go jeszcze raz (bez spacji) albo poproś o nowy."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 34. crm_challenge_fail_options ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_fail_options#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_options"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie udało się zweryfikować konta.\n\nMożesz: spróbować ponownie, poprosić o nowy kod albo połączyć się z obsługą."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 35. crm_challenge_fail_handover ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_fail_handover#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_handover"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Weryfikacja została tymczasowo zablokowana po kilku nieudanych próbach.\n\nSpróbuj ponownie za około 15 minut albo skontaktuj się z recepcją — chętnie pomożemy."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 36. crm_verification_blocked ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_verification_blocked#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_blocked"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Weryfikacja została tymczasowo zablokowana na *{minutes}* min. Spróbuj ponownie później lub skontaktuj się z recepcją."
    },
    "placeholders": {
        "L": [
            {
                "S": "minutes"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 37. crm_challenge_ask_email_code ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_ask_email_code#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_ask_email_code"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Wysłaliśmy kod weryfikacyjny na adres *{email}*. Wpisz go tutaj, aby kontynuować."
    },
    "placeholders": {
        "L": [
            {
                "S": "email"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 38. crm_challenge_email_code_already_sent ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_email_code_already_sent#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_email_code_already_sent"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Kod weryfikacyjny został już wysłany przed chwilą. Sprawdź proszę skrzynkę e‑mail (także SPAM) i spróbuj ponownie za moment."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 39. crm_challenge_missing_email ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_missing_email#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_missing_email"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie mogę znaleźć Twojego adresu e‑mail w systemie. Podaj proszę e‑mail użyty przy zapisie do klubu albo skontaktuj się z recepcją, aby uzupełnić dane."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 40. crm_code_via_email ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_code_via_email#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_code_via_email"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "<p>Twój kod weryfikacyjny to: <strong>{verification_code}</strong><br><br>Kod jest ważny przez {ttl_minutes} minut.<br><br>Jeśli to nie Ty inicjowałeś/aś weryfikację, zignoruj tę wiadomość.</p>"
    },
    "placeholders": {
        "L": [
            {
                "S": "verification_code"
            },
            {
                "S": "ttl_minutes"
            }
        ]
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 41. crm_challenge_expired ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_expired#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_expired"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Kod wygasł. Poproś proszę o nowy kod weryfikacyjny, aby kontynuować."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item

# ==== 42. crm_verification_active ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_verification_active#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_active"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Twoja poprzednia weryfikacja jest nadal aktywna."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 43. system_marketing_optout_confirm ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_confirm#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_confirm"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Czy na pewno chcesz wypisać się z wiadomości marketingowych? Odpowiedz TAK lub NIE."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 44. system_marketing_optin_confirm ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_confirm#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_confirm"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Czy na pewno chcesz zacząć otrzymywać wiadomości marketingowe? Odpowiedz TAK lub NIE."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 45. system_confirm_cancelled ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_confirm_cancelled#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_confirm_cancelled"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "OK, anulowane."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 46. system_marketing_optout_done ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_done#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_done"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Wypisano z wiadomości marketingowych."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 47. system_marketing_optin_done ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_done#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_done"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Zgoda marketingowa została włączona."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item



# ==== 48. system_marketing_change_failed ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_change_failed#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_change_failed"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Nie udało się zmienić zgody. Spróbuj ponownie później."
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item
  
# ==== 49. confirm_words ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#confirm_words#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "confirm_words"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "tak,tak.,potwierdzam,ok,zgadzam się,zgadzam sie,oczywiście,oczywiscie,pewnie,jasne"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws --endpoint-url http://localhost:4566 dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 49. today_words (pl) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#today_words#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "today_words"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "dzisiaj, dziś, dzis"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 49. ticket_more_info (pl) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_more_info#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_more_info"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "Zaraz utworzę dla Ciebie zgłoszenie. Do zgłoszenia załączę historię 10 ostatnich wiadomości. Jeści chcesz coś jeszcze dodać, prosze napisz teraz lub po prostu napisz 'nie'. Dziękuję"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item

# ==== 49. ack_fallback_text (pl) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ack_fallback_text#pl"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ack_fallback_text"
    },
    "language_code": {
        "S": "pl"
    },
    "body": {
        "S": "ok"
    },
    "placeholders": {
        "L": []
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item
