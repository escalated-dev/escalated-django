"""
An import source for tests.

It stands in for a plugin-provided adapter (Zendesk, Freshdesk, ...): core
never talks to a third-party API itself, it only drives whatever the
``import.adapters`` filter hands it.

The records are fixed: two contacts, one tag, three tickets served two to a
page, and two replies. ``on_extract`` lets a test act between batches, for
example to pause the job or to observe the import context.
"""

from escalated.contracts.import_adapter import ImportAdapter
from escalated.support.extract_result import ExtractResult

TOKEN = "secret-token"
CREDENTIALS = {"subdomain": "acme", "api_token": TOKEN}

RECORDS = {
    "contacts": [
        {"source_id": "c1", "email": "ada@customer.test", "name": "Ada Customer"},
        {"source_id": "c2", "email": "bob@customer.test", "name": "Bob Customer"},
    ],
    "tags": [{"source_id": "t1", "name": "Billing"}],
    "tickets": [
        {
            "source_id": "k1",
            "title": "Refund please",
            "description": "Charged twice.",
            "status": "open",
            "priority": "high",
            "requester_source_id": "c1",
            "tag_source_ids": ["t1"],
            "created_at": "2024-01-02T03:04:05Z",
        },
        {
            "source_id": "k2",
            "title": "Login broken",
            "status": "resolved",
            "priority": "urgent",
            "requester_source_id": "c2",
        },
        {"source_id": "k3", "title": "Feature idea", "status": "not-a-status", "requester_source_id": "c1"},
    ],
    "replies": [
        {"source_id": "r1", "ticket_source_id": "k1", "body": "Looking into it", "author_source_id": "c1"},
        {"source_id": "r2", "ticket_source_id": "k2", "body": "Internal note", "is_internal_note": True},
    ],
}

PAGE_SIZE = 2

CREDENTIAL_FIELDS = [
    {"name": "subdomain", "label": "Subdomain", "type": "text", "help": "acme"},
    {"name": "api_token", "label": "API token", "type": "password", "help": ""},
]

TICKET_SOURCE_FIELDS = [
    {"name": "subject", "label": "Subject", "escalated_options": ["title", "description"]},
    {"name": "state", "label": "State", "escalated_options": ["status"]},
]


class FakeImportAdapter(ImportAdapter):
    def __init__(self):
        self.on_extract = None
        self.extract_calls = []
        self.source_field_credentials = None

    def name(self):
        return "fakedesk"

    def display_name(self):
        return "FakeDesk"

    def credential_fields(self):
        return CREDENTIAL_FIELDS

    def test_connection(self, credentials):
        if credentials.get("subdomain") == "down":
            raise RuntimeError("FakeDesk is unreachable")
        return credentials.get("api_token") == TOKEN

    def entity_types(self):
        return list(RECORDS)

    def default_field_mappings(self, entity_type):
        return {"subject": "title", "state": "status"} if entity_type == "tickets" else {}

    def available_source_fields(self, entity_type, credentials):
        self.source_field_credentials = credentials
        return TICKET_SOURCE_FIELDS if entity_type == "tickets" else []

    def extract(self, entity_type, credentials, cursor):
        if credentials.get("api_token") != TOKEN:
            raise RuntimeError("bad credentials")

        self.extract_calls.append((entity_type, cursor))
        if self.on_extract:
            self.on_extract(entity_type, cursor)

        records = RECORDS[entity_type]
        offset = int(cursor or 0)
        page = records[offset : offset + PAGE_SIZE]
        next_offset = offset + PAGE_SIZE

        return ExtractResult(
            records=page,
            cursor=str(next_offset) if next_offset < len(records) else None,
            total_count=len(records),
        )
