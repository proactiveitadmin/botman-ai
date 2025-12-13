# ==== CONFIG ====
$tableName = "Templates-botman-stage"   # <- غيّر اسم الجدول إذا لزم الأمر
$region   = "eu-central-1"              # <- غيّر المنطقة إذا كنت تستخدم أخرى

# ==== 1. handover_to_staff ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#handover_to_staff#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "handover_to_staff"},
    "language_code": {"S": "ar"},
    "body":          {"S": "سأقوم الآن بتحويلك إلى أحد موظفي النادي (سيتم التحويل خلال لحظات)."},
    "placeholders":  {"L": []}
  }'

# ==== 2. ticket_summary ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_summary#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_summary"},
    "language_code": {"S": "ar"},
    "body":          {"S": "طلب العميل"},
    "placeholders":  {"L": []}
  }'

# ==== 3. ticket_created_ok ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_created_ok#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_ok"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لقد أنشأت طلباً جديداً. الرقم: %{ticket}."},
    "placeholders":  {"L": [ { "S": "ticket" } ]}
  }'

# ==== 4. ticket_created_failed ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#ticket_created_failed#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "ticket_created_failed"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تعذّر إنشاء الطلب الآن. يرجى المحاولة مرة أخرى لاحقاً."},
    "placeholders":  {"L": []}
  }'

# ==== 5. clarify_generic ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#clarify_generic#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "clarify_generic"},
    "language_code": {"S": "ar"},
    "body":          {"S": "هل يمكنك توضيح كيف أستطيع مساعدتك؟"},
    "placeholders":  {"L": []}
  }'

# ========== PERFECTGYM – LISTA ZAJĘĆ ==========

# ==== 6. crm_available_classes ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes"},
    "language_code": {"S": "ar"},
    "body":          {"S": "الحصص المتاحة:\n{classes}\n\nاكتب رقم الحصة التي تختارها (مثلاً 1)."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 7. crm_available_classes_empty ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_empty#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_empty"},
    "language_code": {"S": "ar"},
    "body":          {"S": "حالياً لا توجد أي حصص متاحة في الجدول."},
    "placeholders":  {"L": []}
  }'

# ==== 8. crm_available_classes_capacity_no_limit ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_no_limit#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_no_limit"},
    "language_code": {"S": "ar"},
    "body":          {"S": "دون حد لعدد الأماكن"},
    "placeholders":  {"L": []}
  }'

# ==== 9. crm_available_classes_capacity_full ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_full#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_full"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لا توجد أماكن شاغرة (الحد {limit})"},
    "placeholders":  {"L": [ { "S": "limit" } ]}
  }'

# ==== 10. crm_available_classes_capacity_free ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_capacity_free#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_capacity_free"},
    "language_code": {"S": "ar"},
    "body":          {"S": "{free} أماكن شاغرة (الحد {limit})"},
    "placeholders":  {"L": [ { "S": "free" }, { "S": "limit" } ]}
  }'

# ==== 11. crm_available_classes_item ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_item#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_item"},
    "language_code": {"S": "ar"},
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
    "pk":            {"S": "default#crm_available_classes_invalid_index#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_invalid_index"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لم أفهم اختيارك. يرجى إدخال رقم الحصة من 1 إلى {max_index}."},
    "placeholders":  {"L": [ { "S": "max_index" } ]}
  }'

# ==== 13. crm_available_classes_no_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_no_today#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_no_today"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لا توجد أي حصص متاحة اليوم."},
    "placeholders":  {"L": []}
  }'

# ==== 14. crm_available_classes_today ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_today#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_today"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لدينا اليوم الحصص التالية:\n{classes}\n\nاكتب رقم الحصة التي تريدها."},
    "placeholders":  {"L": [ { "S": "classes" } ]}
  }'

# ==== 15. crm_available_classes_no_classes_on_date ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_no_classes_on_date#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_no_classes_on_date"},
    "language_code": {"S": "ar"},
    "body":          {"S": "في تاريخ {date} لا توجد أي حصص متاحة."},
    "placeholders":  {"L": [ { "S": "date" } ]}
  }'

# ==== 16. crm_available_classes_select_by_number ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_available_classes_select_by_number#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_available_classes_select_by_number"},
    "language_code": {"S": "ar"},
    "body":          {"S": "هناك عدة حصص في ذلك اليوم. يرجى كتابة رقم الحصة التي تود حجزها."},
    "placeholders":  {"L": []}
  }'

# ========== PERFECTGYM – KONTRAKT / WERYFIKACJA ==========

# ==== 17. crm_contract_ask_email ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_ask_email#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_ask_email"},
    "language_code": {"S": "ar"},
    "body":          {"S": "يرجى تزويدي بعنوان البريد الإلكتروني المستخدم في النادي حتى أتمكّن من التحقق من حالة عضويتك."},
    "placeholders":  {"L": []}
  }'

# ==== 18. crm_contract_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_not_found#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_not_found"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لا أرى أي عضوية مرتبطة بالبريد الإلكتروني {email} ورقم الهاتف {phone}. يرجى التأكد من أن البيانات مطابقة لتلك المسجلة في PerfectGym."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 19. crm_challenge_ask_dob ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_ask_dob#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_ask_dob"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لأغراض التحقق، يرجى تقديم تاريخ ميلادك (تحقق مؤقت)."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 20. crm_challenge_success ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_success#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_success"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تمّ التحقق من حسابك بنجاح."},
    "placeholders":  {"L": [ { "S": "email" }, { "S": "phone" } ]}
  }'

# ==== 21. crm_contract_details ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_contract_details#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_contract_details"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تفاصيل عضويتك:\nالباقة: {plan_name}\nالحالة:\n{status}\nتاريخ البداية: {start_date}\nتاريخ الانتهاء: {end_date}\nالرصيد الحالي: {current_balance}\nفي حالة الدين منذ: {negative_balance_since}"},
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
    "pk":            {"S": "default#reserve_class_confirmed#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirmed"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تم حجز {class_name} بتاريخ {class_date} الساعة {class_time}. نراك هناك!"},
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
    "pk":            {"S": "default#reserve_class_failed#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_failed"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تعذّر إتمام الحجز. يرجى المحاولة مرة أخرى لاحقاً."},
    "placeholders":  {"L": []}
  }'

# ==== 24. reserve_class_declined ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_declined#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_declined"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تم إلغاء الحجز. أخبرني إذا رغبت في حجز حصة أخرى."},
    "placeholders":  {"L": []}
  }'

# ==== 25. reserve_class_confirm ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm"},
    "language_code": {"S": "ar"},
    "body":          {"S": "هل تؤكد حجز الحصة {class_name} بتاريخ {class_date} في الساعة {class_time}؟  يرجى الرد: نعم أو لا."},
    "placeholders":  {"L": [
      { "S": "class_name" },
      { "S": "class_date" },
      { "S": "class_time" }
    ]}
  }'


# ==== 26. reserve_class_missing_id ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_missing_id#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_missing_id"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تعذّر تحديد الحصة المطلوب حجزها. يرجى المحاولة مرة أخرى."},
    "placeholders":  {"L": []}
  }'

# ==== 27. reserve_class_confirm_words ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_confirm_words#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_confirm_words"},
    "language_code": {"S": "ar"},
    "body":          {"S": "نعم,نعم.,ايوه,أيوه,تمام,موافق,أوافق,أكيد,طبعاً,بالطبع"},
    "placeholders":  {"L": []}
  }'

# ==== 28. reserve_class_decline_words ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#reserve_class_decline_words#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "reserve_class_decline_words"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لا,لا.,إلغاء,ألغِ,أريد الإلغاء,لا أريد,لا أرغب"},
    "placeholders":  {"L": []}
  }'

# ========== WERYFIKACJA WWW / FAQ ==========

# ==== 29. www_not_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_not_verified#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_not_verified"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لم يتم العثور على تحقق فعّال لهذا الرمز."},
    "placeholders":  {"L": []}
  }'

# ==== 30. www_user_not_found ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_user_not_found#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_user_not_found"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لم يتم العثور على عضوية مرتبطة بهذا الرقم."},
    "placeholders":  {"L": []}
  }'

# ==== 31. www_verified ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#www_verified#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "www_verified"},
    "language_code": {"S": "ar"},
    "body":          {"S": "تمّ التحقق من حسابك. يمكنك الآن العودة إلى محادثة الويب."},
    "placeholders":  {"L": []}
  }'

# ==== 32. crm_web_verification_required ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_web_verification_required#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_web_verification_required"},
    "language_code": {"S": "ar"},
    "body":          {"S": "لمتابعة العملية، نحتاج أولاً إلى تأكيد هويتك.\n\nإذا كنت تستخدم محادثة الويب، اضغط على الرابط أدناه لفتح واتساب وإرسال رمز التحقق.\nوإذا كنت بالفعل داخل واتساب، فقط أرسل الرمز الموضح أدناه.\n\nالرمز: {{verification_code}}\nالرابط: {{whatsapp_link}}\n\nبعد إرسال الرمز، عُد إلى هذه المحادثة – سنقوم بالتحقق من حسابك وفتح الوصول إلى بياناتك في PerfectGym."},
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
    "pk":            {"S": "default#faq_no_info#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "faq_no_info"},
    "language_code": {"S": "ar"},
    "body":          {"S": "عذراً، لا تتوفر لدي معلومات حول هذا الموضوع. هل يمكنني مساعدتك في شيء آخر؟"},
    "placeholders":  {"L": []}
  }'

# ========== POWITANIE ==========

# ==== 34. greeting ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#greeting#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "greeting"},
    "language_code": {"S": "ar"},
    "body":          {"S": "مرحباً! أنا المساعد الافتراضي لنادي اللياقة. أخبرني كيف يمكنني مساعدتك."},
    "placeholders":  {"L": []}
  }'

# ==== 35. crm_challenge_retry ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_retry#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_retry"},
    "language_code": {"S": "ar"},
    "body":          {"S": "فشل التحقق. يرجى المحاولة مرة أخرى."},
    "placeholders":  {"L": []}
  }'

# ==== 36. crm_challenge_fail_handover ====
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item '{
    "pk":            {"S": "default#crm_challenge_fail_handover#ar"},
    "tenant_id":     {"S": "default"},
    "template_code": {"S": "crm_challenge_fail_handover"},
    "language_code": {"S": "ar"},
    "body":          {"S": "للأسف لم تنجح عملية التحقق. يرجى المحاولة مرة أخرى في وقت لاحق."},
    "placeholders":  {"L": []}
  }'
