from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class Message:
    tenant_id: str
    from_phone: str
    to_phone: str
    body: str
    channel: str = "whatsapp"
    channel_user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    language_code: Optional[str] = None

@dataclass
class Action:
    type: str
    payload: Dict
