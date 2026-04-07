from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    """
    Normalized representation of an inbound email, independent of the
    source adapter (Mailgun, Postmark, SES, IMAP, etc.).
    """

    from_email: str
    from_name: str | None
    to_email: str
    subject: str
    body_text: str | None
    body_html: str | None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    headers: dict = field(default_factory=dict)
    attachments: list = field(default_factory=list)

    @property
    def body(self) -> str:
        """Return the best available body content (plain text preferred)."""
        return self.body_text or self.body_html or ""
