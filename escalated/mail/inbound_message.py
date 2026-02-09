from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InboundMessage:
    """
    Normalized representation of an inbound email, independent of the
    source adapter (Mailgun, Postmark, SES, IMAP, etc.).
    """

    from_email: str
    from_name: Optional[str]
    to_email: str
    subject: str
    body_text: Optional[str]
    body_html: Optional[str]
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    headers: dict = field(default_factory=dict)
    attachments: list = field(default_factory=list)

    @property
    def body(self) -> str:
        """Return the best available body content (plain text preferred)."""
        return self.body_text or self.body_html or ""
