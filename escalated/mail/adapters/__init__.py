from escalated.mail.adapters.base import BaseAdapter
from escalated.mail.adapters.mailgun import MailgunAdapter
from escalated.mail.adapters.postmark import PostmarkAdapter
from escalated.mail.adapters.ses import SESAdapter
from escalated.mail.adapters.imap import IMAPAdapter

ADAPTERS = {
    "mailgun": MailgunAdapter,
    "postmark": PostmarkAdapter,
    "ses": SESAdapter,
    "imap": IMAPAdapter,
}


def get_adapter(name: str) -> BaseAdapter:
    """
    Return an adapter instance by name.

    Raises ValueError if the adapter name is not recognized.
    """
    adapter_class = ADAPTERS.get(name)
    if adapter_class is None:
        raise ValueError(
            f"Unknown inbound email adapter: '{name}'. "
            f"Must be one of: {', '.join(ADAPTERS.keys())}"
        )
    return adapter_class()


__all__ = [
    "BaseAdapter",
    "MailgunAdapter",
    "PostmarkAdapter",
    "SESAdapter",
    "IMAPAdapter",
    "ADAPTERS",
    "get_adapter",
]
