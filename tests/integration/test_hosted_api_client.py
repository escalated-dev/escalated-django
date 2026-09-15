from unittest.mock import MagicMock, patch

from django.test import override_settings

from escalated.drivers.api_client import HostedApiClient, HostedApiError
from escalated.drivers.synced import SyncedDriver

HOSTED = {"HOSTED_API_URL": "https://cloud.example.test/api/v1", "HOSTED_API_KEY": "sync-token"}


def _ok_response():
    response = MagicMock()
    response.content = b'{"received": true}'
    response.json.return_value = {"received": True}
    response.raise_for_status.return_value = None
    return response


@override_settings(ESCALATED=HOSTED)
def test_emit_posts_named_events_to_the_cloud_events_endpoint():
    with patch("escalated.drivers.api_client.requests.request", return_value=_ok_response()) as request:
        HostedApiClient().emit("ticket.created", {"reference": "ESC-00007", "subject": "Hello"})

    kwargs = request.call_args.kwargs
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://cloud.example.test/api/v1/events"
    assert kwargs["json"]["event"] == "ticket.created"
    assert kwargs["json"]["payload"] == {"reference": "ESC-00007", "subject": "Hello"}
    assert len(kwargs["json"]["event_id"]) == 36
    assert kwargs["json"]["timestamp"]
    assert kwargs["headers"]["Authorization"] == "Bearer sync-token"


@override_settings(ESCALATED=HOSTED)
def test_emit_reuses_a_caller_supplied_event_id_for_retries():
    with patch("escalated.drivers.api_client.requests.request", return_value=_ok_response()) as request:
        HostedApiClient().emit("ticket.updated", {"reference": "ESC-00007"}, event_id="evt-fixed")

    assert request.call_args.kwargs["json"]["event_id"] == "evt-fixed"


@override_settings(ESCALATED=HOSTED)
def test_synced_driver_swallows_cloud_failures_after_the_local_write():
    driver = SyncedDriver()

    with patch.object(HostedApiClient, "emit", side_effect=HostedApiError("cloud is down")) as emit:
        driver._emit_safe("ticket.created", {"reference": "ESC-00007"})

    emit.assert_called_once_with("ticket.created", {"reference": "ESC-00007"})
