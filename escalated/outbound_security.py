import ipaddress
import socket
from urllib.parse import urlparse

from escalated.conf import get_setting


class UnsafeOutboundUrl(ValueError):
    """Raised when an outbound integration URL targets an unsafe destination."""


def validate_outbound_webhook_url(url: str) -> None:
    """
    Reject webhook URLs that can target local or private network resources.

    Outbound webhooks are often configured by privileged users, but treating
    their destination as trusted creates an SSRF path when workflow/admin
    access is compromised or delegated too broadly.
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeOutboundUrl("Webhook URL is required.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeOutboundUrl("Webhook URL must use http or https.")

    if not parsed.hostname:
        raise UnsafeOutboundUrl("Webhook URL must include a hostname.")

    if parsed.username or parsed.password:
        raise UnsafeOutboundUrl("Webhook URL must not include credentials.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeOutboundUrl("Webhook URL includes an invalid port.") from exc

    allow_private = bool(get_setting("ALLOW_PRIVATE_WEBHOOK_URLS"))
    if allow_private:
        return

    hostname = parsed.hostname.rstrip(".")
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeOutboundUrl("Webhook URL hostname could not be resolved.") from exc
        addresses = [ipaddress.ip_address(item[4][0]) for item in addrinfo]

    unsafe_addresses = [addr for addr in addresses if not addr.is_global]
    if unsafe_addresses:
        raise UnsafeOutboundUrl("Webhook URL resolves to a non-public address.")
