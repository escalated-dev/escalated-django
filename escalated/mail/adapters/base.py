import abc

from escalated.mail.inbound_message import InboundMessage


class BaseAdapter(abc.ABC):
    """
    Abstract base class for inbound email adapters.

    Each adapter knows how to:
    1. Verify that an incoming request is authentic (signature checks, etc.)
    2. Parse the request payload into a normalized InboundMessage.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique identifier for this adapter (e.g. 'mailgun', 'postmark')."""
        ...

    @abc.abstractmethod
    def verify_request(self, request) -> bool:
        """
        Verify the authenticity of an incoming webhook request.

        Args:
            request: Django HttpRequest object.

        Returns:
            True if the request is authentic, False otherwise.
        """
        ...

    @abc.abstractmethod
    def parse_request(self, request) -> InboundMessage:
        """
        Parse a Django HttpRequest into a normalized InboundMessage.

        Args:
            request: Django HttpRequest object.

        Returns:
            InboundMessage instance.

        Raises:
            ValueError: If the request payload cannot be parsed.
        """
        ...
