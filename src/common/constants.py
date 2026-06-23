"""Shared constants used across routing, CRM, KB and campaign flows.

Keep module-level names stable: other modules import these constants directly.
"""
import re
from textwrap import dedent


# Campaigns
CAMPAIGNS_TENANT_NEXT_RUN_INDEX = "tenant_next_run_time"
CAMPAIGNS_TIME_ZONE = "Europe/Berlin"
CAMPAIGNS_1ST_NAME_PLACEHOLDER = "first_name"
CAMPAIGNS_PAYMENT_URL_PLACEHOLDER = "payment_link"
CAMPAIGNS_PRODUCT_ID_PLACEHOLDER = "payment_product_id"
CAMPAIGNS_EXCLUDE_TAGS_PLACEHOLDER = "exclude_tags"
CAMPAIGNS_INCLUDE_TAGS_PLACEHOLDER = "include_tags"

# Conversation states
STATE_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATE_AWAITING_VERIFICATION = "awaiting_verification"
STATE_AWAITING_CLASS_SELECTION = "awaiting_class_selection"
STATE_AWAITING_MESSAGE = "awaiting_message"
STATE_AWAITING_CHALLENGE = "awaiting_challenge"
STATE_AWAITING_HANDOVER_COMMENT = "awaiting_handover_comment"
STATE_AWAITING_TICKET_CONFIRMATION = "awaiting_ticket_confirmation"
STATE_AWAITING_TICKET_COMMENT = "awaiting_ticket_comment"

# Channels, sessions and NLU
DEFAULT_CHANNEL = "whatsapp"
WEB_CHANNEL = "web"
SESSION_TIMEOUT_SECONDS = 120
DEFAULT_NLU_CONFIDENCE = 1.0

# CRM confirmation
CRM_CONFIRM_WORDS = "confirm_words"
CRM_REJECT_WORDS = "reject_words"
CRM_CONFIRMED = "confirmed"
CRM_REJECTED = "rejected"
PENDING_CONFIRMATION_TTL_SECONDS = 10 * 60

# CRM verification
OTP_LENGTH = 6
OTP_MAX_ATTEMPTS = 3
CRM_VERIFICATION_TTL_SECONDS = 15 * 60
CRM_VERIFICATION_CODE_SECONDS = 5 * 60
CRM_VERIFICATION_CODE_MINUTES = 5
CRM_COOLDOWN_SECONDS = 30 * 60
CRM_OTP_RESEND_MIN_SECONDS = 60
CRM_MARKETING_AGREEMENT_ID = 1

# CRM classes and date parsing
AVAILABLE_CLASSES_TOP = 10
HISTORY_FETCH_LIMIT = 10
DATE_SLICE_START = 0
DATE_SLICE_END = 10
TIME_SLICE_START = 11
TIME_SLICE_END = 16
CLASS_INDEX_REGEX = r"\b(\d{1,2})\b"
DATE_TIME_REGEX = re.compile(
    r"""
    \b
    (?:
        # yyyy-mm-dd
        (?P<iso_year>\d{4})-(?P<iso_month>\d{1,2})-(?P<iso_day>\d{1,2})

        |

        # dd.mm / dd-mm / dd.mm hh / dd.mm hh:mm
        (?P<day>\d{1,2})[.-](?P<month>\d{1,2})
        (?:
            \s+
            (?P<hour>\d{1,2})
            (?:
                :
                (?P<minute>\d{2})
            )?
        )?
    )
    \b
    """,
    re.VERBOSE,
)

# Knowledge base parsing
QUESTION_SPLIT_REGEX = r"[\n\r;,|/]+\s+|\?+|\.+"
FASTPATCH_SEARCH_REGEX = r"\n\s*A:\s*(.*)$"
FASTPATCH_SPLIT_REGEX = r"\bA:\s*"
SMALLTALK_SEARCH_REGEX = r"[,:;]"
FAQ_FIND_REGEX = r"\w+"
SMALLTALK_SUB1_REGEX = r"[^\w]+$"
SMALLTALK_SUB2_REGEX = r"\s+"
QUESTION_NO_OF_PARTS = 5

# Knowledge base scoring and retrieval
KB_SMALLTALK_MIN_SCORE = 0.35
KB_VECTOR_MIN_SCORE_LOW = 0.43
KB_VECTOR_FASTPATH_MIN_SCORE = 0.50
KB_RETRIEVED_CHUNKS = 6
KB_FETCHED_CHUNKS = 3
SMALLTALK_RETRIEVED_CHUNKS = 1
FAQ_AI_HISTORY_LIMIT = 6

# Knowledge base values
ANSWER_NO_INFO = "__NO_INFO__"
PC_NAME_SMALLTALK = "smalltalk"
PC_NAME_KB = "kb"
STR_CHUNK_SCORE = "score"
FAQ_ANSWER_KEY = "answer"
FAQ_ROLE_USER = "user"
FAQ_NO_KEY_ERR = "NoSuchKey"

# CRM return codes
ENUM_CRM_RETURN_OK = 0
ENUM_CRM_RETURN_ALREADY_BOOKED = 1
ENUM_CRM_RETURN_FAIL = 2

# Intents
INTENT_RESERVE_CLASS = "reserve_class"
INTENT_AVAILABLE_CLASSES = "crm_available_classes"
INTENT_CONTRACT_STATUS = "crm_contract_status"
INTENT_CRM_MEMBER_BALANCE = "crm_member_balance"
INTENT_VERIFICATION = "verification"
INTENT_TICKET = "ticket"
INTENT_HANDOVER = "handover"
INTENT_ACK = "ack"
INTENT_FAQ = "faq"
INTENT_CLARIFY = "clarify"
INTENT_TICKET_STATUS = "ticket_status"
INTENT_MARKETING_OPTOUT = "marketing_optout"
INTENT_MARKETING_OPTIN = "marketing_optin"

INTENTS = (
    INTENT_RESERVE_CLASS,
    INTENT_AVAILABLE_CLASSES,
    INTENT_CONTRACT_STATUS,
    INTENT_CRM_MEMBER_BALANCE,
    INTENT_VERIFICATION,
    INTENT_TICKET,
    INTENT_HANDOVER,
    INTENT_ACK,
    INTENT_FAQ,
    INTENT_CLARIFY,
    INTENT_TICKET_STATUS,
    INTENT_MARKETING_OPTOUT,
    INTENT_MARKETING_OPTIN,
)
_VALID_INTENTS = set(INTENTS)

SENSITIVE_DATA_RULES = (
    "health or medical data",
    "identity or personal data",
    "contact details",
    "financial/payment data",
    "credentials, secrets, MFA codes, API keys",
    "political/religious/ethnic/union data",
    "sexual life/orientation",
    "employee/customer/patient data",
    "confidential business data",
    "source code, infrastructure details",
    "identifying attachments/scans",
)

SENSITIVE_DATA_CATEGORIES = (
    "health",
    "biometric",
    "genetic",
    "identity_document",
    "national_id",
    "address",
    "contact_data",
    "financial",
    "payment_card",
    "credentials",
    "api_secret",
    "mfa_code",
    "political_opinion",
    "religion",
    "ethnicity",
    "trade_union",
    "sexual_life",
    "sexual_orientation",
    "employee_data",
    "customer_data",
    "contract_or_confidential_business_data",
    "source_code_or_system_details",
    "attachment_or_scan",
    "other",
)

REDACTION_PLACEHOLDERS = (
    "[EMAIL]",
    "[PHONE]",
    "[ADDRESS]",
    "[PERSON]",
    "[DOCUMENT]",
    "[ID]",
    "[CARD]",
    "[TOKEN]",
    "[SECRET]",
    "[HEALTH_DATA]",
)

# Used only when LLM/API/parser fails. LLM must use REDACTION_PLACEHOLDERS.
FALLBACK_REDACTED_MESSAGE = "[SENSITIVE_DATA_REDACTED]"


def _bullet_list(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {value}" for value in values)


def _prompt(text: str) -> str:
    return dedent(text).strip() + "\n"


SYSTEM_PROMPT_INTENT = _prompt(
    f"""
    Classify the user message and extract intent + safety flags.

    Return ONLY valid JSON:
    {{
      "intent": "...",
      "confidence": 0.0,
      "slots": {{}},
      "redacted_message": "...",
      "sensitive_data": {{
          "present": false,
          "categories": []
      }}
    }}

    Intents:
    {_bullet_list(INTENTS)}

    Sensitive data:
    Set sensitive_data.present=true if the message contains:
    {_bullet_list(SENSITIVE_DATA_RULES)}

    Categories:
    {_bullet_list(SENSITIVE_DATA_CATEGORIES)}

    Do NOT mark as sensitive:
    - generic discussion
    - public information
    - hypothetical examples
    - topics without identifiable or confidential details

    If sensitive data is present:
    - keep original intent
    - redact sensitive fragments only in redacted_message
    - use placeholders only:
    {_bullet_list(REDACTION_PLACEHOLDERS)}

    Additionally:
    - Return a fully redacted version of the original user message in field:
      redacted_message
    - Preserve meaning and intent.
    - Replace only sensitive fragments.
    - Do NOT remove surrounding context.
    - Preserve original language.
    - Never return raw sensitive values in redacted_message.
    - If multiple values exist, redact all occurrences.

    If sensitive data is absent:
    - present=false
    - categories=[]
    - redacted_message=""

    Intent rules:
    - Message containing only a number -> intent="clarify", confidence=0.01
    - Prefer faq over clarify
    - Urgent issues, lost items, access problems, safety concerns,
      or situations requiring immediate human assistance
      -> intent="ticket"
      
    Slots:
    - optional
    - use only when needed
    - for reserve_class:
      - extract class_id if user provided class identifier or class name
    - otherwise return {{}}

    Short conversational messages:
    - greetings / farewells -> intent="faq", confidence>=0.9
    - acknowledgements -> intent="ack", confidence>=0.9
    never classify these as clarify
    """
)

SYSTEM_PROMPT_FAQ = (
    "You are a helpful customer-support assistant.\n"
    "The user's message may contain multiple questions.\n"
    "If the user message includes a greeting and a question, prioritize answering the question.\n"
    "Conversation history is provided only for resolving references (e.g., pronouns). "
    "It MUST NOT be used as a knowledge source.\n"
    "Answer using ONLY the Knowledge snippets below.\n"
    "- If snippets clearly support an answer, answer that part.\n"
    "- If snippets do NOT clearly support an answer, do NOT guess.\n"
)
SYSTEM_PROMPT_FAQ_JSON = (
    f'Output MUST be valid JSON with exactly one key: "{FAQ_ANSWER_KEY}". No other keys.\n'
    "Knowledge snippets:\n"
)
SYSTEM_PROMPT_FAQ_STRICT = (
    f'- If the snippets do not clearly answer the user\'s request, respond with the exact JSON '
    f'{{"{FAQ_ANSWER_KEY}":"{ANSWER_NO_INFO}"}}.\n'
    "- If ANY snippet explicitly answers the question, you MUST answer using that snippet.\n"
)
SYSTEM_PROMPT_FAQ_NO_STRICT = (
    "- Instead, ask ONE short clarifying question that would allow finding the answer "
    "in the knowledge base.\n"
)
SYSTEM_PROMPT_LANG_FIRST = "\nAnswer in the language "
SYSTEM_PROMPT_LANG_SECOND = " (ISO language code)."
SYSTEM_PROMPT_NO_LANG = "\nAnswer in the same language as the user's question."
SYSTEM_PROMPT_HISTORY = (
    "- Conversation history is provided only for resolving references (e.g., pronouns). "
    "It MUST NOT be used as a knowledge source."
)

# AI messages
FAQ_MSG_JSON = f'Respond strictly in JSON with a single key "{FAQ_ANSWER_KEY}".'
