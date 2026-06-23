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



# ==== 2.1. ticket_description ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_description#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_description"
    },
    "language_code": {
        "S": "en"
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
        "S": "Thank you — your request has been created. Case number: *{ticket}*. We’ll get back to you as soon as it’s reviewed."
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
        "S": "I couldn’t create the request. Please try again in a moment — and if the problem persists, contact reception at +48111111111."
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
        "S": "Could you specify what your issue is about? (e.g. membership, payment, classes, booking, app)"
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
        "S": "At the moment, I can’t see any available classes in the schedule. Please try again later or contact reception."
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
        "S": "I can’t find an active account for the provided details. Please check whether the email (*{email}*) or phone number (*{phone}*) matches the information used when registering with the club."
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
        "S": "Here are your membership details:\n\n• Plan: *{plan_name}*\n• Status: *{status}*\n• Valid from: *{start_date}*\n• Valid until: *{end_date}*\n"
    },
    "placeholders": {
        "L": [
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
        "S": "clubProactiveIT#crm_contract_negative_balance#en"
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
        "S": "Here are your membership details:\n\n• Plan: *{plan_name}*\n• Status: *{status}*\n• Valid from: *{start_date}*\n• Valid until: *{end_date}*\n• Balance: *{current_balance}*\n•• Negative balance since: *{negative_balance_since}*\n\nType *YES* if you would like to pay the outstanding amount."
    },
    "placeholders": {
        "L": [
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
        "S": "I’m not able to link this chat with your club account yet. If you’d like to access account-related information (e.g. membership, payments, bookings), please contact reception."
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
        "S": "clubProactiveIT#crm_member_balance_negative#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_member_balance_negative"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your current balance is: *{current_balance}*. Type *YES* if you would like to pay the outstanding amount."
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
        "S": "Your current balance is: *{current_balance}*."
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
        "S": "All set — your booking is confirmed ✅\n\n*{class_name}* — {class_date} at {class_time}."
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
        "S": "I couldn’t book the class. Please try again in a moment."
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
        "S": "Okay — I won’t book it. If you change your mind, let me know."
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
        "S": "clubProactiveIT#web_crm_not_available#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "web_crm_not_available"
    },
    "language_code": {
        "S": "en"
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
        "S": "I can’t find this information in the FAQ. Is there anything else I can help you with?"
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
        "S": "Please try again and enter the verification code."
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
        "S": "I couldn’t verify the account.\n\nYou can: try again or connect with support."
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
        "S": "Verification is temporarily blocked. Please wait about *{minutes}* min and try again later, or contact reception."
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
        "S": "Before you continue, I need to verify it's really you. Enter the code sent to *{email}*."
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
        "S": "I can’t find your email address in the system. Please contact reception to update your details."
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
        "S": "<p>Your verification code is: <strong>{verification_code}</strong><br><br>The code is valid for {ttl_minutes} minutes.<br><br>If you didn’t request this verification, please ignore this message.</p>"
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


# ==== 42. crm_verification_active ====

  $item = @'
{
    "pk": {
        "S": "clubProactiveIT#crm_verification_active#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "crm_verification_active"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your previous verification is still active."
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

# ==== 43. system_marketing_optout_confirm (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_confirm#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_confirm"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Are you sure you want to unsubscribe from marketing messages? Reply YES or NO."
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


# ==== 44. system_marketing_optin_confirm (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_confirm#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_confirm"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Are you sure you want to start receiving marketing messages? Reply YES or NO."
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


# ==== 45. system_confirm_cancelled (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_confirm_cancelled#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_confirm_cancelled"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "OK, cancelled."
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


# ==== 46. system_marketing_optout_done (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optout_done#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optout_done"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "You have been unsubscribed from marketing messages."
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


# ==== 47. system_marketing_optin_done (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_optin_done#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_optin_done"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Marketing consent has been enabled."
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


# ==== 48. system_marketing_change_failed (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#system_marketing_change_failed#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "system_marketing_change_failed"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "We couldn’t change your consent. Please try again later."
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

# ==== 49. reject_words (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#reject_words#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "reject_words"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "no,no.,reject,decline,cancel,stop,nope,never,not interested,i don't want,i do not want"
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
# ==== 49. confirm_words (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#confirm_words#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "confirm_words"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "yes,yes.,confirm,ok,okay,sure,course,certainly,good"
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

# ==== 49. today_words (EN) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#today_words#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "today_words"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "today"
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


# ==== 49. ticket_more_info (en) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ticket_more_info#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_more_info"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "I will create a ticket for you shortly. I will attach the history of the last 10 messages to the ticket. If you would like to add anything else, please write now or simply type 'no'. Thank you."
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

# ==== 49. ack_fallback_text (en) ====

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#ack_fallback_text#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ack_fallback_text"
    },
    "language_code": {
        "S": "en"
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

$item = @'
{
    "pk": {
        "S": "clubProactiveIT#payment_link_generated#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "payment_link_generated"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Your payment link:\n\n{url}"
    },
    "placeholders": {
        "L": [
            {
                "S": "url"
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
        "S": "clubProactiveIT#payment_link_generation_failed#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "payment_link_generation_failed"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Sorry, but the payment link could not be generated. Please try again later or contact reception."
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
        "S": "clubProactiveIT#ticket_confirm_create#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_confirm_create"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "Would you like me to create a support request for the reception desk? Reply: yes or no."
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
        "S": "clubProactiveIT#ticket_cancelled#en"
    },
    "tenant_id": {
        "S": "clubProactiveIT"
    },
    "template_code": {
        "S": "ticket_cancelled"
    },
    "language_code": {
        "S": "en"
    },
    "body": {
        "S": "OK, I have not created the request. If you change your mind, just send another message."
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