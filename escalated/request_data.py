"""
The fields a view was sent, whether the browser posted a form or JSON.

The shared frontend (``@escalated-dev/escalated``) submits with Inertia's
``useForm().post()``/``router.post()``, which send ``application/json``.
Django only parses form encodings into ``request.POST``, so a view that reads
``request.POST`` sees nothing from those pages. :func:`request_data` gives
such views one object with the ``QueryDict`` methods they already call.
"""

import json

from django.utils.datastructures import MultiValueDict, MultiValueDictKeyError

_CACHE_ATTRIBUTE = "_escalated_request_data"


def _text(value):
    """A JSON value as the text a form field would carry."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        # Views json.loads() structured fields (conditions, actions, schedule...).
        return json.dumps(value)
    return str(value)


def _values(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value]
    return [_text(value)]


class JsonData(MultiValueDict):
    """
    A JSON object body behind the ``QueryDict`` reading API.

    ``get``/``[]`` return the field as text (``true``/``false`` for booleans,
    ``""`` for null, JSON for objects and arrays) and ``getlist`` returns an
    array field's items, so views written for form posts read JSON unchanged.
    The parsed object stays available as :attr:`raw`.
    """

    def __init__(self, data):
        self.raw = dict(data)
        super().__init__({key: _values(value) for key, value in self.raw.items()})

    def __getitem__(self, key):
        if key not in self.raw:
            raise MultiValueDictKeyError(key)
        return _text(self.raw[key])

    def get(self, key, default=None):
        return self[key] if key in self.raw else default

    def __contains__(self, key):
        return key in self.raw

    def items(self):
        for key in self.raw:
            yield key, self[key]

    def values(self):
        for key in self.raw:
            yield self[key]

    def dict(self):
        return {key: self[key] for key in self.raw}

    def copy(self):
        return JsonData(self.raw)


def is_json(request):
    return (request.content_type or "").split(";")[0].strip().lower() == "application/json"


def request_data(request):
    """
    The submitted fields: a JSON object body as :class:`JsonData`, otherwise
    ``request.POST``. A JSON body that is not an object reads as empty.
    """
    if not is_json(request):
        return request.POST
    cached = getattr(request, _CACHE_ATTRIBUTE, None)
    if cached is None:
        try:
            parsed = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        cached = JsonData(parsed if isinstance(parsed, dict) else {})
        setattr(request, _CACHE_ATTRIBUTE, cached)
    return cached
