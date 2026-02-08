import logging
from urllib.parse import urljoin

import requests

from escalated.conf import get_setting

logger = logging.getLogger("escalated")


class HostedApiClient:
    """
    HTTP client for server-to-server communication with the Escalated cloud API.
    Used by the synced and cloud drivers.
    """

    def __init__(self):
        self.base_url = get_setting("HOSTED_API_URL")
        self.api_key = get_setting("HOSTED_API_KEY")
        self.timeout = 30  # seconds

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "escalated-django/0.1.0",
        }

    def _url(self, path):
        """Build a full API URL from a relative path."""
        base = self.base_url.rstrip("/") + "/"
        return urljoin(base, path.lstrip("/"))

    def _request(self, method, path, data=None, params=None):
        """
        Perform an HTTP request and return the parsed JSON response.
        Raises HostedApiError on failure.
        """
        url = self._url(path)
        try:
            response = requests.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.Timeout:
            logger.error(f"Escalated API timeout: {method} {url}")
            raise HostedApiError(f"API request timed out: {method} {url}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Escalated API connection error: {method} {url}: {e}")
            raise HostedApiError(f"Cannot connect to API: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Escalated API HTTP error: {method} {url}: {e}")
            error_body = {}
            try:
                error_body = e.response.json()
            except (ValueError, AttributeError):
                pass
            raise HostedApiError(
                f"API returned {e.response.status_code}: "
                f"{error_body.get('message', str(e))}",
                status_code=e.response.status_code,
                response_body=error_body,
            )

    # ----- Ticket endpoints -----

    def create_ticket(self, data):
        return self._request("POST", "/tickets", data=data)

    def update_ticket(self, ticket_id, data):
        return self._request("PATCH", f"/tickets/{ticket_id}", data=data)

    def get_ticket(self, ticket_id):
        return self._request("GET", f"/tickets/{ticket_id}")

    def list_tickets(self, params=None):
        return self._request("GET", "/tickets", params=params)

    def transition_status(self, ticket_id, status):
        return self._request(
            "POST", f"/tickets/{ticket_id}/status", data={"status": status}
        )

    def assign_ticket(self, ticket_id, agent_id):
        return self._request(
            "POST",
            f"/tickets/{ticket_id}/assign",
            data={"agent_id": agent_id},
        )

    def unassign_ticket(self, ticket_id):
        return self._request("POST", f"/tickets/{ticket_id}/unassign")

    # ----- Reply endpoints -----

    def add_reply(self, ticket_id, data):
        return self._request("POST", f"/tickets/{ticket_id}/replies", data=data)

    # ----- Tag endpoints -----

    def add_tags(self, ticket_id, tag_ids):
        return self._request(
            "POST", f"/tickets/{ticket_id}/tags", data={"tag_ids": tag_ids}
        )

    def remove_tags(self, ticket_id, tag_ids):
        return self._request(
            "DELETE", f"/tickets/{ticket_id}/tags", data={"tag_ids": tag_ids}
        )

    # ----- Department endpoints -----

    def change_department(self, ticket_id, department_id):
        return self._request(
            "POST",
            f"/tickets/{ticket_id}/department",
            data={"department_id": department_id},
        )

    # ----- Priority endpoints -----

    def change_priority(self, ticket_id, priority):
        return self._request(
            "POST",
            f"/tickets/{ticket_id}/priority",
            data={"priority": priority},
        )

    # ----- Sync endpoint -----

    def emit(self, event_type, payload):
        """
        Emit an event to the cloud for syncing purposes.
        Used by the SyncedDriver after each local operation.
        """
        return self._request(
            "POST",
            "/sync/events",
            data={"event": event_type, "payload": payload},
        )


class HostedApiError(Exception):
    """Exception raised when the hosted API returns an error."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}
