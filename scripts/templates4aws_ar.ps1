# ==== KONFIGURACJA ====
$tableName = "Templates-botman-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"              # <- jeśli używasz innego, zmień
# ==== 1. handover_to_staff ====
  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#handover_to_staff#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "handover_to_staff"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "سأقوم الآن بتحويل طلبك إلى الاستقبال. إذا كان الأمر عاجلًا، يمكنك أيضًا زيارة الاستقبال أو الاتصال بالنادي."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_summary#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_summary"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "طلب إلى الاستقبال"
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_created_ok#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_ok"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "شكرًا لك — تم إنشاء الطلب. رقم التذكرة: *{ticket}*. سنعود إليك بمجرد مراجعته."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


# ==== 2.1. ticket_description ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_description#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_description"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "Request from chat.\nLast message:\n{body}\nHistory:\n{history_block}"
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_created_failed#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_failed"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تعذّر إنشاء الطلب. يرجى المحاولة مرة أخرى بعد قليل. إذا تكرر الأمر، أخبرني بما يحدث وسأحوّله إلى الاستقبال."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#clarify_generic#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "clarify_generic"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "أكيد — هل يمكنك توضيح الموضوع؟ (مثل: الاشتراك، الدفع، الحصص، الحجز، التطبيق)"
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "هذه هي الحصص المتاحة:\n\n{classes}\n"
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_empty#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_empty"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أرى حصصًا متاحة حاليًا. جرّب لاحقًا، أو أخبرني باليوم والوقت المفضلين لديك وسأبحث عن بدائل."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_no_limit#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_no_limit"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "بدون حد للمقاعد"
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_full#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_full"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا توجد أماكن متاحة (الحد {limit})"
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_capacity_free#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_free"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "*{free}* أماكن متاحة (الحد {limit})"
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_item#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_item"
    },
    "language_code": {
        "S": "ar-AE"
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_invalid_index#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_invalid_index"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لم أتمكن من مطابقة اختيارك. يرجى إرسال رقم من 1 إلى {max_index}."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_no_today#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_today"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أرى حصصًا متاحة اليوم. إذا رغبت، أرسل التاريخ وسأتحقق من يوم آخر."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_today#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_today"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "الحصص المتاحة اليوم:\n\n{classes}\n\nاختر رقمًا من القائمة وسأساعدك في الحجز."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_no_classes_on_date#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_classes_on_date"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أرى حصصًا متاحة بتاريخ *{date}*. إذا رغبت، أرسل تاريخًا آخر أو وقتًا مفضلًا وسأتحقق مرة أخرى."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_available_classes_select_by_number#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_select_by_number"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "يرجى اختيار الحصة بإرسال رقمها من القائمة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_contract_not_found#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_not_found"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لم أتمكن من العثور على اشتراك فعّال لك في النظام. إذا كنت تعتقد أن هذا خطأ، تواصل مع الاستقبال — ويمكنني أيضًا إنشاء طلب للتحقق."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_success#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_success"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "ممتاز — تم التحقق بنجاح ✅ يمكننا المتابعة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_contract_details#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_details"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "هذه تفاصيل اشتراكك:\n\n• الخطة: *{plan_name}*\n• الحالة: *{status}*\n• سارية من: *{start_date}*\n• سارية حتى: *{end_date}*\n\nإذا كانت هناك أي معلومة غير صحيحة، أخبرني وسأساعدك بالتواصل مع الاستقبال."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_member_not_linked#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_not_linked"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا يمكنني ربط حسابك بملف العضوية بعد. يرجى إكمال التحقق أو التواصل مع الاستقبال لتحديث بياناتك."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_member_balance#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_balance"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "رصيدك الحالي هو: *{current_balance}*.\n\nإذا كانت لديك أسئلة حول المبالغ، يمكنني مساعدتك في توضيح سبب هذا الرصيد."
    },
    "placeholders": {
        "L": [
            {
                "S": "current_balance"
            }
        ]
    }
}
'@
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_confirmed#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirmed"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تم — تم تأكيد الحجز ✅\n\n*{class_name}* — {class_date} الساعة {class_time}\n\nإذا رغبت في الإلغاء أو تغيير الموعد، أخبرني وسأساعدك."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_already_booked#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_already_booked"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "يبدو أنك مسجل/ة بالفعل في هذه الحصة.\n\n*{class_name}* — {class_date} الساعة {class_time}\n\nإذا رغبت، يمكنني التحقق من مواعيد أخرى أو حصص مشابهة بها أماكن متاحة."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_failed#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_failed"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تعذّر حجز الحصة. يرجى المحاولة مرة أخرى بعد قليل. إذا تكرر الخطأ، أرسل اسم الحصة والتاريخ وسأحوّله إلى الاستقبال."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_declined#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_declined"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "حسنًا — لن أقوم بالحجز. إذا غيرت رأيك، أرسل رقم الحصة من القائمة وسنكمل."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_confirm#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirm"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "هل تريد حجز:\n\n*{class_name}* — {class_date} الساعة {class_time}؟\n\nأجب: *نعم* / *لا*."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_missing_id#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_missing_id"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أملك معرّف الحصة، لذلك لا أستطيع إكمال الحجز. يرجى اختيار الحصة من القائمة (بالرقم) وسنجرب مرة أخرى."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_not_verified#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_not_verified"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "حسابك غير مُتحقَّق منه بعد. يرجى إكمال التحقق للمتابعة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_user_not_found#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_user_not_found"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لم أتمكن من العثور على حسابك. تحقق من بياناتك وحاول مرة أخرى، أو تواصل مع الاستقبال للمساعدة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#www_verified#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_verified"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "شكرًا لك — تم التحقق من حسابك. يمكننا المتابعة 😊"
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#web_crm_not_available#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "web_crm_not_available"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "هذه الميزة متاحة فقط عبر قناة واتساب. يُرجى استخدام واتساب للمتابعة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#faq_no_info#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "faq_no_info"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أرى هذه المعلومة في الأسئلة الشائعة. إذا رغبت، يمكنني تحويل السؤال إلى الاستقبال أو إرشادك لمكان التحقق (مثل التطبيق)."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_retry#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_retry"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "يرجى المحاولة مرة أخرى وإدخال رمز التحقق. إذا لم يكن لديك رمز، اطلب رمزًا جديدًا."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_fail_options#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_options"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تعذّر التحقق من الحساب.\n\nيمكنك: المحاولة مرة أخرى، طلب رمز جديد، أو التواصل مع الدعم."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_fail_handover#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_handover"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تم حظر التحقق مؤقتًا بعد عدة محاولات غير ناجحة.\n\nيرجى المحاولة بعد حوالي 15 دقيقة أو التواصل مع الاستقبال."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_verification_blocked#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_blocked"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "التحقق محظور مؤقتًا. يرجى الانتظار حوالي *{minutes}* دقيقة ثم المحاولة لاحقًا، أو التواصل مع الاستقبال."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_ask_email_code#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_ask_email_code"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "أرسلنا رمز تحقق إلى *{email}*. أدخله هنا للمتابعة."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_email_code_already_sent#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_email_code_already_sent"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "تم إرسال رمز تحقق قبل قليل. يرجى التحقق من بريدك الإلكتروني (وأيضًا الرسائل غير المرغوب فيها) ثم المحاولة بعد لحظة."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_missing_email#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_missing_email"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "لا أستطيع العثور على عنوان بريدك الإلكتروني في النظام. يرجى تزويدي بالبريد المستخدم عند التسجيل في النادي، أو التواصل مع الاستقبال لتحديث بياناتك."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_code_via_email#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_code_via_email"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "<p>رمز التحقق الخاص بك هو: <strong>{verification_code}</strong><br><br>الرمز صالح لمدة {ttl_minutes} دقيقة.<br><br>إذا لم تطلب هذا التحقق، يرجى تجاهل هذه الرسالة.</p>"
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_challenge_expired#ar-AE"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_expired"
    },
    "language_code": {
        "S": "ar-AE"
    },
    "body": {
        "S": "انتهت صلاحية الرمز. يرجى طلب رمز تحقق جديد للمتابعة."
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


# ==== 42. crm_verification_active ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_verification_active#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_active"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "لا تزال عملية التحقق السابقة الخاصة بك نشطة."
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

# ==== 43. system_marketing_optout_confirm (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_confirm#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_confirm"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "هل أنت متأكد أنك تريد إلغاء الاشتراك في الرسائل التسويقية؟ رد بنعم أو لا."
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


# ==== 44. system_marketing_optin_confirm (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_confirm#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_confirm"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "هل أنت متأكد أنك تريد استلام الرسائل التسويقية؟ رد بنعم أو لا."
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


# ==== 45. system_confirm_cancelled (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_confirm_cancelled#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_confirm_cancelled"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "تمام، تم الإلغاء."
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


# ==== 46. system_marketing_optout_done (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_done#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_done"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "تم إلغاء اشتراكك من الرسائل التسويقية."
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


# ==== 47. system_marketing_optin_done (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_done#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_done"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "تم تفعيل الموافقة على الرسائل التسويقية."
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


# ==== 48. system_marketing_change_failed (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_change_failed#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_change_failed"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "ما قدرنا نغيّر الموافقة. حاول مرة ثانية لاحقاً."
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

# ==== 49. confirm_words (AR) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#confirm_words#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "confirm_words"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "نعم,نعم.,ايوه,أيوه,تمام,موافق,أوافق,أكيد,طبعاً,بالطبع"
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

# ==== 49. today_words (ar) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#today_words#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "today_words"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "اليوم"
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



# ==== 49. ticket_more_info (ar) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_more_info#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_more_info"
    },
    "language_code": {
        "S": "ar"
    },
    "body": {
        "S": "سأقوم الآن بإنشاء بلاغ لك. سأرفق مع البلاغ سجل آخر 10 رسائل. إذا كنت ترغب في إضافة أي شيء آخر، يرجى الكتابة الآن أو فقط اكتب 'لا'. شكرًا لك."
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

# ==== 49. ack_fallback_text (ar) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ack_fallback_text#ar"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ack_fallback_text"
    },
    "language_code": {
        "S": "ar"
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
