"""
Pure-function tests for escalated.mail.message_id_util. Mirrors the
NestJS / Spring / WordPress / .NET / Phoenix / Laravel / Rails
reference test suites.
"""

from escalated.mail.message_id_util import (
    build_message_id,
    build_reply_to,
    parse_ticket_id_from_message_id,
    verify_reply_to,
)

DOMAIN = "support.example.com"
SECRET = "test-secret-long-enough-for-hmac"


def test_build_message_id_initial_ticket():
    assert build_message_id(42, None, DOMAIN) == "<ticket-42@support.example.com>"


def test_build_message_id_reply_form():
    assert build_message_id(42, 7, DOMAIN) == "<ticket-42-reply-7@support.example.com>"


def test_parse_ticket_id_round_trips_initial():
    assert parse_ticket_id_from_message_id(build_message_id(42, None, DOMAIN)) == 42


def test_parse_ticket_id_round_trips_reply():
    assert parse_ticket_id_from_message_id(build_message_id(42, 7, DOMAIN)) == 42


def test_parse_ticket_id_accepts_value_without_brackets():
    assert parse_ticket_id_from_message_id("ticket-99@example.com") == 99


def test_parse_ticket_id_returns_none_for_nil_or_empty():
    assert parse_ticket_id_from_message_id(None) is None
    assert parse_ticket_id_from_message_id("") is None


def test_parse_ticket_id_returns_none_for_unrelated_input():
    assert parse_ticket_id_from_message_id("<random@mail.com>") is None
    assert parse_ticket_id_from_message_id("ticket-abc@example.com") is None


def test_build_reply_to_is_stable():
    first = build_reply_to(42, SECRET, DOMAIN)
    again = build_reply_to(42, SECRET, DOMAIN)
    assert first == again
    import re

    assert re.match(r"^reply\+42\.[a-f0-9]{8}@support\.example\.com$", first)


def test_build_reply_to_differs_across_tickets():
    a = build_reply_to(42, SECRET, DOMAIN)
    b = build_reply_to(43, SECRET, DOMAIN)
    assert a.split("@")[0] != b.split("@")[0]


def test_verify_reply_to_round_trips():
    address = build_reply_to(42, SECRET, DOMAIN)
    assert verify_reply_to(address, SECRET) == 42


def test_verify_reply_to_accepts_local_part_only():
    address = build_reply_to(42, SECRET, DOMAIN)
    local = address.split("@")[0]
    assert verify_reply_to(local, SECRET) == 42


def test_verify_reply_to_rejects_tampered_signature():
    address = build_reply_to(42, SECRET, DOMAIN)
    at = address.index("@")
    local = address[:at]
    last = local[-1]
    tampered = local[:-1] + ("1" if last == "0" else "0") + address[at:]
    assert verify_reply_to(tampered, SECRET) is None


def test_verify_reply_to_rejects_wrong_secret():
    address = build_reply_to(42, SECRET, DOMAIN)
    assert verify_reply_to(address, "different-secret") is None


def test_verify_reply_to_rejects_malformed_input():
    assert verify_reply_to(None, SECRET) is None
    assert verify_reply_to("", SECRET) is None
    assert verify_reply_to("alice@example.com", SECRET) is None
    assert verify_reply_to("reply@example.com", SECRET) is None
    assert verify_reply_to("reply+abc.deadbeef@example.com", SECRET) is None


def test_verify_reply_to_case_insensitive_hex():
    address = build_reply_to(42, SECRET, DOMAIN)
    assert verify_reply_to(address.upper(), SECRET) == 42
