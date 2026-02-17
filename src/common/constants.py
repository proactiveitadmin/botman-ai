import os

STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATE_AWAITING_VERIFICATION = "awaiting_verification"
STATE_AWAITING_CLASS_SELECTION = "awaiting_class_selection"
STATE_AWAITING_MESSAGE = "awaiting_message"
STATE_AWAITING_CHALLENGE = "awaiting_challenge"
STATE_AWAITING_HANDOVER_COMMENT = "awaiting_handover_comment"
STATE_AWAITING_TICKET_COMMENT = "awaiting_ticket_comment"

SESSION_TIMEOUT_SECONDS = 120
DEFAULT_NLU_CONFIDENCE = 1.0
DEFAULT_CHANNEL = "whatsapp"
WEB_CHANNEL = "web"
OTP_LENGTH=6
OTP_MAX_ATTEMPTS = 3
CRM_VERIFICATION_TTL_SECONDS = 15 * 60 
CRM_VERIFICATION_CODE_SECONDS = 5 * 60 
CRM_VERIFICATION_CODE_MINUTES = 5
CRM_COOLDOWN_SECONDS = 30 * 60 
CRM_OTP_RESEND_MIN_SECONDS = 60
CRM_MARKETING_AGREEMENT_ID = 1
AVAILABLE_CLASSES_TOP = 10 
HISTORY_FETCH_LIMIT = 10
DATE_SLICE_START = 0
DATE_SLICE_END = 10
TIME_SLICE_START = 11
TIME_SLICE_END = 16
CLASS_INDEX_REGEX=r"\b(\d{1,2})\b"
ISO_DATE_REGEX=r"\b(\d{4}-\d{2}-\d{2})\b"

#KB
QUESTION_SPLIT_REGEX=r"[\n\r;,|/]+\s+|\?+|\.+"
FASTPATCH_SEARCH_REGEX=r"\n\s*A:\s*(.*)$"
FASTPATCH_SPLIT_REGEX=r"\bA:\s*"
SMALLTALK_SEARCH_REGEX=r"[,:;]"
FAQ_FIND_REGEX=r"\w+"
SMALLTALK_SUB1_REGEX=r"[^\w]+$"
SMALLTALK_SUB2_REGEX=r"\s+"
QUESTION_NO_OF_PARTS=5
ANSWER_NO_INFO="__NO_INFO__"
PC_NAME_SMALLTALK="smalltalk"
PC_NAME_KB="kb"
FAQ_AI_HISTORY_LIMIT=6
STR_CHUNK_SCORE="score"
ENUM_CRM_RETURN_OK=0
ENUM_CRM_RETURN_ALREADY_BOOKED=1
ENUM_CRM_RETURN_FAIL=2
FAQ_ANSWER_KEY = "answer"
FAQ_ROLE_USER = "user"
FAQ_NO_KEY_ERR = "NoSuchKey"

#intents
INTENT_RESERVE_CLASS="reserve_class"
INTENT_FAQ="faq"
INTENT_HANDOVER="handover"
INTENT_VERIFICATION="verification"
INTENT_CLARIFY="clarify"
INTENT_TICKET="ticket"
INTENT_TICKET_STATUS="ticket_status"
INTENT_AVAILABLE_CLASSES="crm_available_classes"
INTENT_CONTRACT_STATUS="crm_contract_status"
INTENT_CRM_MEMBER_BALANCE="crm_member_balance"
INTENT_ACK="ack"
INTENT_MARKETING_OPTOUT="marketing_optout"
INTENT_MARKETING_OPTIN="marketing_optin"


_VALID_INTENTS = {
    INTENT_RESERVE_CLASS,
    INTENT_FAQ,
    INTENT_HANDOVER,
    INTENT_VERIFICATION,
    INTENT_CLARIFY,
    INTENT_TICKET,
    INTENT_TICKET_STATUS,
    INTENT_AVAILABLE_CLASSES,
    INTENT_CONTRACT_STATUS,
    INTENT_CRM_MEMBER_BALANCE,
    INTENT_ACK,
    INTENT_MARKETING_OPTOUT,
    INTENT_MARKETING_OPTIN,
}

#mozliwe ze musi isc na per tenant
KB_SMALLTALK_MIN_SCORE = 0.35
KB_VECTOR_MIN_SCORE_LOW = 0.43
KB_VECTOR_FASTPATH_MIN_SCORE = 0.50

KB_RETRIEVED_CHUNKS = 6
KB_FETCHED_CHUNKS = 3
SMALLTALK_RETRIEVED_CHUNKS = 1

#PROMPTS
SYSTEM_PROMPT_INTENT = """
Classify the user message and extract intent + slots.

Return ONLY JSON:
{"intent": "...", "confidence": 0..1, "slots": {}}

Intents:
- reserve_class
- crm_available_classes
- crm_contract_status
- crm_member_balance
- verification
- ticket
- handover
- ack
- faq
- clarify
- ticket_status
- marketing_optout
- marketing_optin

Rules:
- If message is only a number -> intent=clarify (confidence 0.01)
- Prefer faq over clarify
- Messages describing urgent problems, lost items, access to personal belongings,
  safety issues, or situations requiring immediate human assistance
  MUST be classified as intent INTENT_TICKET.
  
Conversational shortcuts:
- Single-token or very short greetings, farewells, and politeness expressions
  (e.g. greetings, goodbyes, thanks, acknowledgements) are HIGH confidence.
- For such messages, set confidence >= 0.9.
- These messages are NOT ambiguous and should not be classified as clarify.

If the message is a greeting or farewell:
- Use intent "faq".
- These messages are HIGH confidence (>= 0.9).

If the message is a short acknowledgement
(e.g. confirming or reacting to a previous message):
- Use intent INTENT_ACK.
- These messages are HIGH confidence (>= 0.9).
"""

SYSTEM_PROMPT_FAQ = ( 
        "You are a helpful customer-support assistant.\n"
        "The user's message may contain multiple questions.\n"
        "If the user message includes a greeting and a question, prioritize answering the question.\n"
        "Conversation history is provided only for resolving references (e.g., pronouns). It MUST NOT be used as a knowledge source.\n"
        "Answer using ONLY the Knowledge snippets below.\n"
        "- If snippets clearly support an answer, answer that part.\n"
        "- If snippets do NOT clearly support an answer, do NOT guess.\n" )
SYSTEM_PROMPT_FAQ_JSON = ( "Output MUST be valid JSON with exactly one key: \"answer\". No other keys.\n"
        "Knowledge snippets:\n" )
SYSTEM_PROMPT_FAQ_STRICT = ( "- If the snippets do not clearly answer the user's request, respond with the exact JSON {\"answer\":\"__NO_INFO__\"}.\n"
        "- If ANY snippet explicitly answers the question, you MUST answer using that snippet.\n" )
SYSTEM_PROMPT_FAQ_NO_STRICT = "- Instead, ask ONE short clarifying question that would allow finding the answer in the knowledge base.\n"

SYSTEM_PROMPT_FAQ_OLD = (
        "You are a helpful customer-support assistant.\n"
        "Answer the user's question ONLY using the FAQ entries below.\n"
        "Always respond as a JSON object with a single key \"answer\".\n"
        "In the \"answer\" value, paraphrase the relevant information. "
        "If the FAQ does not contain the information needed to answer the question, "
        "reply that you don't know AND ask the user if there is anything else you can help with.\n"
        "FAQ entries:\n" )


SYSTEM_PROMPT_LANG_FIRST =  f"\nAnswer in the language "
SYSTEM_PROMPT_LANG_SECOND =  f" (ISO language code)."
SYSTEM_PROMPT_NO_LANG = "\nAnswer in the same language as the user's question."
SYSTEM_PROMPT_HISTORY = (
                "- Conversation history is provided only for resolving references (e.g., pronouns)."
                "It MUST NOT be used as a knowledge source."
            )

#AI MSG
FAQ_MSG_JSON = 'Respond strictly in JSON with a single key FAQ_ANSWER_KEY.'