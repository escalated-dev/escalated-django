import logging
import mimetypes

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from escalated.conf import get_setting
from escalated.models import Attachment

logger = logging.getLogger("escalated")


class AttachmentService:
    """
    Manages file attachments for tickets and replies.
    """

    @staticmethod
    def attach(content_object, file, original_filename=None):
        """
        Attach a file to a ticket or reply.

        Args:
            content_object: The Ticket or Reply instance to attach to
            file: A Django UploadedFile or file-like object
            original_filename: Override filename (defaults to file.name)

        Returns:
            Attachment instance

        Raises:
            ValidationError: If file exceeds size limit or attachment count
        """
        max_size_kb = get_setting("MAX_ATTACHMENT_SIZE_KB")
        max_attachments = get_setting("MAX_ATTACHMENTS")

        # Determine filename
        filename = original_filename or getattr(file, "name", "unnamed")

        # Check file size
        file_size = getattr(file, "size", 0)
        if file_size > max_size_kb * 1024:
            raise ValidationError(
                f"File '{filename}' exceeds maximum size of {max_size_kb}KB. "
                f"Got {file_size / 1024:.1f}KB."
            )

        # Check attachment count
        ct = ContentType.objects.get_for_model(content_object)
        existing_count = Attachment.objects.filter(
            content_type=ct, object_id=content_object.pk
        ).count()

        if existing_count >= max_attachments:
            raise ValidationError(
                f"Maximum of {max_attachments} attachments reached for this item."
            )

        # Detect mime type
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        attachment = Attachment.objects.create(
            content_type=ct,
            object_id=content_object.pk,
            file=file,
            original_filename=filename,
            mime_type=mime_type,
            size=file_size,
        )

        logger.info(
            f"Attachment '{filename}' ({mime_type}, {file_size}B) added to "
            f"{ct.model} #{content_object.pk}"
        )

        return attachment

    @staticmethod
    def get_attachments(content_object):
        """Get all attachments for a content object."""
        ct = ContentType.objects.get_for_model(content_object)
        return Attachment.objects.filter(
            content_type=ct, object_id=content_object.pk
        )

    @staticmethod
    def delete_attachment(attachment_id):
        """Delete an attachment by ID."""
        try:
            attachment = Attachment.objects.get(pk=attachment_id)
            # Delete the file from storage
            if attachment.file:
                attachment.file.delete(save=False)
            attachment.delete()
            logger.info(f"Attachment #{attachment_id} deleted")
            return True
        except Attachment.DoesNotExist:
            return False
