# ==== CONFIG ====
$tableName = "Templates-botman-stage"   # <- change to your table name if needed
$region   = "eu-central-1"              # <- change if you use a different region

# ==== 1. handover_to_staff ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#handover_to_staff#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "handover_to_staff"},
    "language_code": {"S": "en"},
    "body":          {"S": "I am connecting you with a club staff member (you will be switched over shortly)."},
    "placeholders":  {"L": []}
  }'

# ==== 2. ticket_summary ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_summary#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_summary"},
    "language_code": {"S": "en"},
    "body":          {"S": "Customer ticket"},
    "placeholders":  {"L": []}
  }'

# ==== 3. ticket_created_ok ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_created_ok#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_ok"},
    "language_code": {"S": "en"},
    "body":          {"S": "I have created a ticket for you. Number: %{ticket}."},
    "placeholders":  {"L": [ { "S": "ticket" } ]}
  }'

# ==== 4. ticket_created_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_created_failed#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_failed"},
    "language_code": {"S": "en"},
    "body":          {"S": "I was not able to create a ticket. Please try again later."},
    "placeholders":  {"L": []}
  }'

# ==== 5. clarify_generic ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#clarify_generic#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "clarify_generic"},
    "language_code": {"S": "en"},
    "body":          {"S": "Could you please clarify how I can help you?"},
    "placeholders":  {"L": []}
  }'

# ========== PERFECTGYM – LISTA ZAJĘĆ ==========

# ==== 6. crm_available_classes ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes"},
    "language_code": {"S": "en"},
    "body":          {"S": "Available classes:\n{classes}\n\nPlease type the number of the class you choose (e.g. 1)."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 7. crm_available_classes_empty ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_empty#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_empty"},
    "language_code": {"S": "en"},
    "body":          {"S": "I cannot see any available classes in the schedule at the moment."},
    "placeholders":  {"L": []}
  }'

# ==== 8. crm_available_classes_capacity_no_limit ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_no_limit#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_no_limit"},
    "language_code": {"S": "en"},
    "body":          {"S": "no limit on places"},
    "placeholders":  {"L": []}
  }'

# ==== 9. crm_available_classes_capacity_full ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_full#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_full"},
    "language_code": {"S": "en"},
    "body":          {"S": "no places available (limit {limit})"},
    "placeholders":  {"L": [ { "S": "limit" } ]}
  }'

# ==== 10. crm_available_classes_capacity_free ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_free#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_free"},
    "language_code": {"S": "en"},
    "body":          {"S": "{free} places available (limit {limit})"},
    "placeholders":  {"L": [ { "S": "free" }, { "S": "limit" } ]}
  }'

# ==== 11. crm_available_classes_item ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_item#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_item"},
    "language_code": {"S": "en"},
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

# ==== 12. crm_available_classes_invalid_index ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_invalid_index#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_invalid_index"},
    "language_code": {"S": "en"},
    "body":          {"S": "I did not understand your choice. Please enter a class number from 1 to {max_index}."},
    "placeholders":  {"L": [ { "S": "max_index" } ]}
  }'

# ==== 13. crm_available_classes_no_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_no_today#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_no_today"},
    "language_code": {"S": "en"},
    "body":          {"S": "There are no available classes today."},
    "placeholders":  {"L": []}
  }'

# ==== 14. crm_available_classes_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_today#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_today"},
    "language_code": {"S": "en"},
    "body":          {"S": "Today we have these classes:\n{classes}\n\nPlease type the number of the class you choose."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 15. crm_available_classes_no_classes_on_date ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_no_classes_on_date#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_no_classes_on_date"},
    "language_code": {"S": "en"},
    "body":          {"S": "On {date} there are no available classes."},
    "placeholders":  {"L": [ { "S": "date" } ]}
  }'

# ==== 16. crm_available_classes_select_by_number ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_select_by_number#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_select_by_number"},
    "language_code": {"S": "en"},
    "body":          {"S": "There are several classes on that day. Please type the number of the class you would like to book."},
    "placeholders":  {"L": []}
  }'

# ========== PERFECTGYM – KONTRAKT / WERYFIKACJA ==========

# ==== 17. crm_contract_ask_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_ask_email#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_ask_email"},
    "language_code": {"S": "en"},
    "body":          {"S": "Please provide the email address you use at the club so I can check the status of your membership."},
    "placeholders":  {"L": []}
  }'

# ==== 18. crm_contract_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_not_found#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_not_found"},
    "language_code": {"S": "en"},
    "body":          {"S": "I cannot see any membership linked to the email {email} and phone number {phone}. Please make sure your details match those in PerfectGym."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 19. crm_challenge_ask_dob ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_ask_dob#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_ask_dob"},
    "language_code": {"S": "en"},
    "body":          {"S": "For verification purposes, please provide your date of birth (temporary verification)"},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 20. crm_challenge_success ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_success#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_success"},
    "language_code": {"S": "en"},
    "body":          {"S": "Your account has been successfully verified."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 21. crm_contract_details ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_details#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_details"},
    "language_code": {"S": "en"},
    "body":          {"S": "Here are your membership details:\nPlan: {plan_name}\nStatus: {status}\nStart: {start_date}\nEnd: {end_date}\nCurrent balance: {current_balance}\nIn debt since: {negative_balance_since}"},
    "placeholders":  {
      "L": [
        { "S": "plan_name" },
        { "S": "status" },
        { "S": "start_date" },
        { "S": "end_date" },
        { "S": "current_balance" },
        { "S": "negative_balance_since" }
      ]
    }
  }'

# ========== REZERWACJE ZAJĘĆ ==========

# ==== 22. reserve_class_confirmed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirmed#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirmed"},
    "language_code": {"S": "en"},
    "body":          {"S": "{class_name} has been booked for {class_date} at {class_time}. See you then!"},
    "placeholders":  {
      "L": [
        { "S": "class_name" },
        { "S": "class_date" },
        { "S": "class_time" }
      ]
    }
  }'

# ==== 23. reserve_class_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_failed#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_failed"},
    "language_code": {"S": "en"},
    "body":          {"S": "I could not complete the booking. Please try again later."},
    "placeholders":  {"L": []}
  }'

# ==== 24. reserve_class_declined ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_declined#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_declined"},
    "language_code": {"S": "en"},
    "body":          {"S": "The booking has been cancelled. Let me know if you would like to book another class."},
    "placeholders":  {"L": []}
  }'

# ==== 25. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm"},
    "language_code": {"S": "en"},
    "body":          {"S": "Do you confirm the booking for class {class_name} on {class_date} at {class_time}? Please reply: YES or NO."},
    "placeholders":  {"L": [ { "S": "class_name" },
							 { "S": "class_date" },
							 { "S": "class_time" }
						]}
  }'

# ==== 26. reserve_class_missing_id ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_missing_id#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_missing_id"},
    "language_code": {"S": "en"},
    "body":          {"S": "I was not able to identify which class to book. Please try again."},
    "placeholders":  {"L": []}
  }'

# ==== 27. reserve_class_confirm_words ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm_words#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm_words"},
    "language_code": {"S": "en"},
    "body":          {"S": "yes,yes.,confirm,I confirm,ok,okay,sure,of course,certainly,no problem,all good"},
    "placeholders":  {"L": []}
  }'

# ==== 28. reserve_class_decline_words ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_decline_words#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_decline_words"},
    "language_code": {"S": "en"},
    "body":          {"S": "no,no.,cancel,I cancel,abort,I do not want"},
    "placeholders":  {"L": []}
  }'

# ========== WERYFIKACJA WWW / FAQ ==========

# ==== 29. www_not_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_not_verified#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_not_verified"},
    "language_code": {"S": "en"},
    "body":          {"S": "No active verification was found for this code."},
    "placeholders":  {"L": []}
  }'

# ==== 30. www_user_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_user_not_found#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_user_not_found"},
    "language_code": {"S": "en"},
    "body":          {"S": "No membership linked to this number was found."},
    "placeholders":  {"L": []}
  }'

# ==== 31. www_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_verified#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_verified"},
    "language_code": {"S": "en"},
    "body":          {"S": "Your account has been verified. You can now return to the web chat."},
    "placeholders":  {"L": []}
  }'

# ==== 32. crm_web_verification_required ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_web_verification_required#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_web_verification_required"},
    "language_code": {"S": "en"},
    "body":          {"S": "To continue, we need to confirm your identity.\n\nIf you are using the web chat, click the link below to open WhatsApp and send the verification code.\nIf you are already in WhatsApp, simply send the code below.\n\nCode: {{verification_code}}\nLink: {{whatsapp_link}}\n\nAfter sending the code, return to this conversation – we will verify your account and unlock access to your PerfectGym data."},
    "placeholders":  {
      "L": [
        { "S": "verification_code" },
        { "S": "whatsapp_link" }
      ]
    }
  }'

# ==== 33. faq_no_info ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#faq_no_info#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "faq_no_info"},
    "language_code": {"S": "en"},
    "body":          {"S": "Sorry, I do not have information about that. Can I help you with anything else?"},
    "placeholders":  {"L": []}
  }'

# ========== POWITANIE ==========

# ==== 34. greeting ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#greeting#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "greeting"},
    "language_code": {"S": "en"},
    "body":          {"S": "Hi! I am the virtual assistant of the fitness club. Tell me how I can help you."},
    "placeholders":  {"L": []}
  }'

# ==== 35. crm_challenge_retry ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_retry#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_retry"},
    "language_code": {"S": "en"},
    "body":          {"S": "Verification failed. Please try again."},
    "placeholders":  {"L": []}
  }'

# ==== 36. crm_challenge_fail_handover ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_fail_handover#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_fail_handover"},
    "language_code": {"S": "en"},
    "body":          {"S": "“Verification has been temporarily blocked. Please try again in 15 minutes or contact customer support.”"},
    "placeholders":  {"L": []}
  }'

# ==== CRM: crm_challenge_ask_email_code ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_ask_email_code#en"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_ask_email_code"},
    "language_code": {"S": "en"},
    "body":          {"S": "We’ve sent a verification code to {{email}}. Please enter it here to continue."},
    "placeholders":  {"L": [{"S": "email"}]}
  }'

