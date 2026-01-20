# ==== KONFIGURACJA ====
$tableName = "Templates-botman-stage"   # <- PODMIEŃ NA SWOJĄ NAZWĘ TABELI
$region   = "eu-central-1"              # <- jeśli używasz innego, zmień
# ==== 1. handover_to_staff ====
  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#handover_to_staff#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "handover_to_staff"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I’m forwarding your request to the front desk. If it’s urgent, you can also visit reception or call the club."
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
        "S": "clubProactiveIT#ticket_summary#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_summary"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Request to the front desk"
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
        "S": "clubProactiveIT#ticket_created_ok#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_ok"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Thank you — your request has been created. Case number: %{ticket}. We’ll get back to you as soon as it’s reviewed."
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


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_created_failed#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_created_failed"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t create the request. Please try again in a moment. If it keeps happening, tell me what’s going on and I’ll pass it to the front desk."
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
        "S": "clubProactiveIT#clarify_generic#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "clarify_generic"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Sure — could you please clarify what this is about? (e.g., membership, payment, classes, booking, app)"
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
        "S": "clubProactiveIT#crm_available_classes#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Here are the available classes:\n\n{classes}\n"
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
        "S": "clubProactiveIT#crm_available_classes_empty#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_empty"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I don’t see any available classes right now. Please try again later, or tell me your preferred day and time and I’ll check alternatives."
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
        "S": "clubProactiveIT#crm_available_classes_capacity_no_limit#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_no_limit"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "no limit"
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
        "S": "clubProactiveIT#crm_available_classes_capacity_full#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_full"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "no spots left (limit {limit})"
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
        "S": "clubProactiveIT#crm_available_classes_capacity_free#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_capacity_free"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "*{free}* spots left (limit {limit})"
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
        "S": "clubProactiveIT#crm_available_classes_item#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_item"
    },
    "language_code": {
        "S": "en"
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
        "S": "clubProactiveIT#crm_available_classes_invalid_index#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_invalid_index"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t match that choice. Please send a class number from 1 to {max_index}."
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
        "S": "clubProactiveIT#crm_available_classes_no_today#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_today"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I don’t see any available classes for today. If you’d like, tell me the date and I’ll check another day."
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
        "S": "clubProactiveIT#crm_available_classes_today#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_today"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Available today:\n\n{classes}\n\nChoose a number from the list and I’ll help you book."
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
        "S": "clubProactiveIT#crm_available_classes_no_classes_on_date#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_no_classes_on_date"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I don’t see any available classes on *{date}*. If you’d like, tell me a different date or preferred time and I’ll check again."
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
        "S": "clubProactiveIT#crm_available_classes_select_by_number#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_available_classes_select_by_number"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Please pick a class by sending its number from the list."
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
        "S": "clubProactiveIT#crm_contract_not_found#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_not_found"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t find an active membership for you in the system. If you think this is a mistake, please contact reception — I can also create a request for them to verify it."
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
        "S": "clubProactiveIT#crm_challenge_success#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_success"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Great — verification completed ✅ We can continue."
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
        "S": "clubProactiveIT#crm_contract_details#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_contract_details"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Here are your membership details:\n\n• Plan: *{plan_name}*\n• Status: *{status}*\n• Valid from: *{start_date}*\n• Valid until: *{end_date}*\n\nIf anything looks incorrect, let me know — I’ll help clarify it with reception."
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
        "S": "clubProactiveIT#crm_member_not_linked#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_not_linked"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I can’t link your account to a club member profile yet. Please complete verification, or contact reception to update your details."
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
        "S": "clubProactiveIT#crm_member_balance#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_balance"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your current balance is: *{balance}*.\n\nIf you have questions about charges, I can also help explain what this amount comes from."
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
aws dynamodb put-item `
  --table-name $tableName `
  --region $region `
  --item $item


  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#reserve_class_confirmed#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirmed"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "All set — your booking is confirmed ✅\n\n*{class_name}* — {class_date} at {class_time}\n\nIf you’d like to cancel or change the time, tell me — I’ll help."
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
        "S": "clubProactiveIT#reserve_class_already_booked#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_already_booked"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Looks like you’re already booked for this class.\n\n*{class_name}* — {class_date} at {class_time}\n\nIf you want, I can check other times or similar classes with available spots."
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
        "S": "clubProactiveIT#reserve_class_failed#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_failed"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t book the class. Please try again in a moment. If it keeps failing, tell me the class name and date and I’ll pass it to reception."
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
        "S": "clubProactiveIT#reserve_class_declined#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_declined"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Okay — I won’t book it. If you change your mind, send the class number from the list and we’ll continue."
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
        "S": "clubProactiveIT#reserve_class_confirm#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_confirm"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Do you want to book:\n\n*{class_name}* — {class_date} at {class_time}?\n\nReply: *yes* / *no*."
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
        "S": "clubProactiveIT#reserve_class_missing_id#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reserve_class_missing_id"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I don’t have the class ID, so I can’t finish the booking. Please choose a class from the list (number) and we’ll try again."
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
        "S": "clubProactiveIT#www_not_verified#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_not_verified"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your account is not verified yet. Please complete verification to continue."
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
        "S": "clubProactiveIT#www_user_not_found#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_user_not_found"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t find your account. Double-check your details and try again, or contact reception for help."
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
        "S": "clubProactiveIT#www_verified#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "www_verified"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Thank you — your account has been verified. We can continue 😊"
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
        "S": "clubProactiveIT#crm_web_verification_required#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_web_verification_required"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "To continue, I need to verify your account. I’ll send a verification code to your email address."
    },
    "placeholders": {
        "L": [
            {
                "S": "verification_code"
            },
            {
                "S": "whatsapp_link"
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
        "S": "clubProactiveIT#faq_no_info#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "faq_no_info"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I don’t see this information in the FAQ. If you want, I can pass the question to reception or suggest where to check it (e.g., in the app)."
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
        "S": "clubProactiveIT#crm_challenge_retry#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_retry"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Please try again and enter the verification code. If you don’t have a code, ask for a new one."
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
        "S": "clubProactiveIT#crm_challenge_fail_options#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_options"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I couldn’t verify the account.\n\nYou can: try again, request a new code, or connect with support."
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
        "S": "clubProactiveIT#crm_challenge_fail_handover#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_fail_handover"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Verification has been temporarily blocked after several failed attempts.\n\nPlease try again in about 15 minutes, or contact reception."
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
        "S": "clubProactiveIT#crm_verification_blocked#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_blocked"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Verification is temporarily blocked. Please wait about {{minutes}} min and try again later, or contact reception."
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
        "S": "clubProactiveIT#crm_challenge_ask_email_code#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_ask_email_code"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "We’ve sent a verification code to {{email}}. Enter it here to continue."
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
        "S": "clubProactiveIT#crm_challenge_email_code_already_sent#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_email_code_already_sent"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "A verification code was just sent. Please check your email (also Spam/Junk) and try again in a moment."
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
        "S": "clubProactiveIT#crm_challenge_missing_email#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_missing_email"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I can’t find your email address in the system. Please provide the email you used when registering at the club, or contact reception to update your details."
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
        "S": "clubProactiveIT#crm_code_via_email#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_code_via_email"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your verification code is: {{verification_code}}\n\nThe code is valid for {{ttl_minutes}} minutes.\n\nIf you didn’t request this verification, please ignore this message."
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
        "S": "clubProactiveIT#crm_challenge_expired#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_challenge_expired"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "The code has expired. Please request a new verification code to continue."
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

