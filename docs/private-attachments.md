# Private attachments

Ticket and reply attachments are stored through Django's default storage under
`escalated/attachments/<year>/<month>/`. Escalated never hands out the file's
MEDIA URL. Every serialized attachment (`AttachmentSerializer`, the REST API's
`ApiAttachmentSerializer`) carries a `url` that points to the package's
download view:

```
<ROUTE_PREFIX>/attachments/<id>/?token=<signed token>
```

The route is registered whether or not the UI is enabled.

## Who can download

The token is signed with `SECRET_KEY` and expires after
`ESCALATED["ATTACHMENT_DOWNLOAD_TTL_MINUTES"]` minutes (default 10, clamped
to 1 to 60). Expiry applies to agents too. A valid token is not enough: the
download also needs current access to the attachment's ticket.

| Requester of the download | Ticket and public-reply attachments | Internal-note attachments |
|---|---|---|
| Agent or admin who can view the ticket (department and account visibility apply) | yes | yes |
| The ticket's requester | yes | no |
| A guest, from a link issued by their guest ticket page | yes | no |
| Anyone else | no | no |

Browser downloads use the host session. API and mobile clients send their
Escalated bearer token (`Authorization: Bearer ...`); a supplied token that is
invalid or expired gets 401 and never falls back to the session.

Guest links carry a capability bound to the ticket's guest credential, so
rotating that credential revokes every link already issued. Attachments whose
ticket or reply has been deleted, and files missing from storage, return 404.

Refresh the ticket to get a new link after one expires.

## Responses

- `Content-Disposition: attachment`, with the original filename reduced to a
  basename without control characters or quotes.
- `Content-Type` is the stored type only for `application/pdf`, `image/gif`,
  `image/jpeg`, `image/png`, `image/webp` and `text/plain`; anything else is
  sent as `application/octet-stream`.
- `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store,
  max-age=0` and `Referrer-Policy: no-referrer`.

## Do not serve the attachment folder publicly

Signed links protect nothing if the file is also reachable at its MEDIA URL.
Make sure `MEDIA_ROOT/escalated/attachments/` is not served by your web
server, Django's `static()` helper, a CDN or a public bucket policy. For
example, with nginx serving `/media/`:

```nginx
location /media/escalated/attachments/ { return 404; }
```

On S3-compatible storage, keep the objects private (for django-storages:
`default_acl = "private"`, `querystring_auth = True`) and do not put a public
CDN in front of the `escalated/attachments/` prefix.

Upgrading does not move existing files. Block the public path before you rely
on the new access checks, then clear any CDN copies and confirm that an old
public URL no longer returns the file.

## Host-rendered templates

If your own templates link to attachments, use
`escalated.attachment_access.download_url(attachment)` rather than
`attachment.file.url`.
