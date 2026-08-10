"""Subida de fotos de evidencia a Cloudflare R2 (docs/desarrollo.md sección 1.1 / 2.1).

R2 es S3-compatible, así que se usa boto3 apuntando al endpoint de la cuenta. Todo el
conocimiento sobre R2 (cliente, armado del key y de la URL pública) vive acá: la vista
solo pide "subí este archivo y devolveme la URL".
"""

import logging
import mimetypes
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)

# Extensiones aceptadas para la foto de evidencia. Se usan solo para armar el nombre
# del objeto en R2; la validación de que el archivo sea una imagen la hace el serializer.
_ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}
_DEFAULT_SUFFIX = ".jpg"


class EvidenceUploadError(APIException):
    """R2 no aceptó el archivo. 502: el error es del almacenamiento, no del cliente."""

    status_code = 502
    default_detail = "No se pudo subir la foto al almacenamiento. Intentá de nuevo."
    default_code = "evidence_upload_failed"


def get_r2_client():
    """Cliente boto3 apuntando al endpoint S3 de la cuenta de R2."""
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY,
        aws_secret_access_key=settings.R2_SECRET_KEY,
        # R2 no tiene regiones: usa siempre "auto" y firma v4.
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def _suffix_for(upload):
    """Extensión del objeto en R2, a partir del nombre original o del content type."""
    suffix = Path(upload.name or "").suffix.lower()
    if suffix in _ALLOWED_SUFFIXES:
        return suffix
    guessed = mimetypes.guess_extension(upload.content_type or "") or ""
    return guessed.lower() if guessed.lower() in _ALLOWED_SUFFIXES else _DEFAULT_SUFFIX


def build_evidence_key(shipment, evidence_type, upload):
    """Key del objeto en el bucket, scopeado por empresa y remito.

    El nombre original NO se reutiliza (puede traer acentos, espacios o repetirse):
    se usa un uuid4 y se conserva solo la extensión.
    """
    return (
        f"evidence/{shipment.company_id}/{shipment.pk}/"
        f"{evidence_type}/{uuid.uuid4().hex}{_suffix_for(upload)}"
    )


def build_file_url(key):
    """URL que se guarda en Evidence.file_url."""
    return f"{settings.R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"


def upload_evidence_file(upload, shipment, evidence_type):
    """Sube la foto a R2 y devuelve la URL pública del objeto.

    Si R2 falla, propaga EvidenceUploadError (502) para que la vista no cree un
    registro de Evidence apuntando a un archivo que no existe.
    """
    key = build_evidence_key(shipment, evidence_type, upload)
    extra_args = {}
    if upload.content_type:
        extra_args["ContentType"] = upload.content_type

    try:
        get_r2_client().upload_fileobj(
            upload, settings.R2_BUCKET_NAME, key, ExtraArgs=extra_args
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception(
            "Fallo la subida de evidencia a R2 (remito #%s, key %s): %s",
            shipment.pk,
            key,
            exc,
        )
        raise EvidenceUploadError() from exc

    return build_file_url(key)
