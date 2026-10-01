import logging
import os
import uuid

from flask import request
from flask_restful import abort
from werkzeug.utils import secure_filename

from sqldesk import features, models, redis_connection, settings, uploads
from sqldesk.handlers.base import BaseResource, get_object_or_404
from sqldesk.permissions import require_admin

logger = logging.getLogger(__name__)


def _get_extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class DataSourceUploadListResource(BaseResource):
    @require_admin
    def get(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        uploads = models.UploadedFile.query.filter(models.UploadedFile.data_source_id == data_source.id).order_by(
            models.UploadedFile.created_at.desc()
        )
        return [upload.to_dict() for upload in uploads]

    @require_admin
    def post(self, data_source_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)

        if data_source.type != "duckdb":
            abort(400, message="File uploads are only supported for DuckDB data sources.")

        max_size_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
        if request.content_length and request.content_length > max_size_bytes:
            abort(413, message="File exceeds the maximum allowed size of {} MB.".format(settings.UPLOAD_MAX_SIZE_MB))

        file = request.files.get("file")
        if file is None or file.filename == "":
            abort(400, message="No file provided.")

        original_filename = secure_filename(file.filename)
        extension = _get_extension(original_filename)
        if extension not in settings.UPLOAD_ALLOWED_EXTENSIONS:
            abort(
                400,
                message="Unsupported file type '{}'. Allowed types: {}.".format(
                    extension, ", ".join(sorted(settings.UPLOAD_ALLOWED_EXTENSIONS))
                ),
            )

        # Checked on the declared length first, so an upload that cannot fit is
        # refused before the bytes are written. Checked again below on what
        # actually arrived, because content-length is a claim.
        if request.content_length:
            problem = uploads.why_this_would_not_fit(self.current_org, request.content_length)
            if problem:
                abort(413, message=problem)

        display_name = (request.form.get("name") or "").strip() or None

        # Computed and checked *before* constructing the UploadedFile below: assigning
        # `data_source=` on a new UploadedFile cascades it into the session immediately
        # (via the relationship), so querying afterwards would autoflush that pending
        # insert first and the row would always collide with itself.
        candidate_view_name = models.UploadedFile.sanitize_view_name(display_name or original_filename)
        existing_view_names = {
            u.view_name for u in models.UploadedFile.query.filter(models.UploadedFile.data_source_id == data_source.id)
        }
        if candidate_view_name in existing_view_names:
            abort(
                400,
                message='A table named "{}" already exists for this data source. '
                "Choose a different name, or delete the existing one first.".format(candidate_view_name),
            )

        upload = models.UploadedFile(
            org=self.current_org,
            data_source=data_source,
            filename=original_filename,
            display_name=display_name,
            stored_filename="{}.{}".format(uuid.uuid4().hex, extension),
            content_type=file.content_type,
            created_by=self.current_user,
            expires_at=models.UploadedFile.default_expiry(),
        )

        # Flush so org_id/data_source_id (set via the relationships above) and the
        # generated id are populated before they're used to build the storage path.
        models.db.session.add(upload)
        models.db.session.flush()

        os.makedirs(upload.directory, exist_ok=True)
        destination = upload.path
        file.save(destination)
        upload.size = os.path.getsize(destination)

        if upload.size > max_size_bytes:
            os.remove(destination)
            models.db.session.rollback()
            abort(413, message="File exceeds the maximum allowed size of {} MB.".format(settings.UPLOAD_MAX_SIZE_MB))

        # On what arrived rather than what was declared. The row is pending in
        # this session but not committed, so `bytes_held` does not count it --
        # which is why the new size is passed in rather than assumed.
        problem = uploads.why_this_would_not_fit(self.current_org, upload.size)
        if problem:
            os.remove(destination)
            models.db.session.rollback()
            abort(413, message=problem)

        models.db.session.commit()
        redis_connection.delete(data_source._schema_key)

        self.record_event(
            {
                "action": "upload_file",
                "object_id": data_source.id,
                "object_type": "datasource",
                "filename": original_filename,
            }
        )

        return upload.to_dict()


class DataSourceUploadKeepResource(BaseResource):
    """
    Make one upload permanent, or let it expire again.

    Its own permission rather than admin-only: deciding what is worth keeping
    on the disk is the job of whoever uploaded the data, and an administrator
    who has to approve every CSV is an administrator who approves all of them.
    """

    def post(self, data_source_id, upload_id):
        upload = self._upload(data_source_id, upload_id)
        if not features.can(self.current_user, features.KEEP_UPLOADS):
            abort(
                403,
                message="Keeping a file permanently is a permission an administrator grants to a group.",
            )
        upload.keep(self.current_user)
        models.db.session.commit()
        self.record_event({"action": "keep_upload", "object_id": upload.id, "object_type": "uploaded_file"})
        return upload.to_dict()

    def delete(self, data_source_id, upload_id):
        """Put it back on the clock, starting from now."""
        upload = self._upload(data_source_id, upload_id)
        if not features.can(self.current_user, features.KEEP_UPLOADS):
            abort(403, message="That is a permission an administrator grants to a group.")
        upload.expires_at = models.UploadedFile.default_expiry()
        upload.kept_at = None
        upload.kept_by = None
        upload.expiry_warning_sent_at = None
        models.db.session.commit()
        self.record_event({"action": "unkeep_upload", "object_id": upload.id, "object_type": "uploaded_file"})
        return upload.to_dict()

    def _upload(self, data_source_id, upload_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        upload = get_object_or_404(models.UploadedFile.get_by_id_and_org, upload_id, self.current_org)
        if upload.data_source_id != data_source.id:
            abort(404)
        return upload


class DataSourceUploadResource(BaseResource):
    @require_admin
    def delete(self, data_source_id, upload_id):
        data_source = get_object_or_404(models.DataSource.get_by_id_and_org, data_source_id, self.current_org)
        upload = get_object_or_404(models.UploadedFile.get_by_id_and_org, upload_id, self.current_org)

        if upload.data_source_id != data_source.id:
            abort(404)

        upload.delete()
        redis_connection.delete(data_source._schema_key)

        self.record_event(
            {
                "action": "delete_file",
                "object_id": data_source.id,
                "object_type": "datasource",
                "filename": upload.filename,
            }
        )

        return "", 204
