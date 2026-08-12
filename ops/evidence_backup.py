"""Copia de respaldo de las fotos de evidencia a un segundo bucket (tarea 7.2).

Las fotos SON el producto: el remito restaurado de un backup de base que apunta a una
foto que ya no existe no prueba nada. El dump de la 7.1 guarda las URLs, no los bytes,
así que la evidencia necesita su propia copia.

Por qué un job y no versionado o replicación del bucket:
  - **Versionado**: R2 no lo implementa. Verificado contra el bucket real —
    `list_object_versions` responde `501 NotImplemented` (no un 403 de permisos, que es
    lo que devuelven las llamadas de configuración de bucket con el token de la app).
    Sin API para listar ni recuperar versiones anteriores, no hay de dónde restaurar.
  - **Replicación**: R2 no ofrece replicación bucket a bucket como sí hace S3. Lo que
    tiene son herramientas para migrar HACIA R2 (Super Slurper, Sippy), que es el
    problema inverso.
  - Queda el job periódico, que además tiene una propiedad que la replicación no da:
    **acá nunca se borra nada del destino**. Una replicación que propaga el borrado
    replica también el error que esta tarea intenta cubrir.

Reglas de este módulo:
  - **Solo copia; NUNCA borra del bucket de backup.** Es lo que hace que un borrado por
    error en el bucket principal sea recuperable. El destino solo crece.
  - **Nunca pisa un objeto que ya existe** — ni en el destino al copiar, ni en el
    origen al restaurar. Las keys de evidencia llevan un uuid4 y son inmutables
    (`shipments/storage.build_evidence_key`), así que una key que ya está es la misma
    foto, no una versión nueva.

El procedimiento de recuperación está en `BACKUP.md`, sección 7.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class EvidenceBackupError(RuntimeError):
    """Falló alguna etapa de la copia. El comando la traduce a un exit code != 0."""


# --- Clientes ---------------------------------------------------------------


def get_source_client():
    """Cliente del bucket de evidencia (el principal, donde escribe la app)."""
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY,
        aws_secret_access_key=settings.R2_SECRET_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def get_backup_client():
    """Cliente del bucket de respaldo de las fotos.

    Token propio, scopeado solo a ese bucket: la credencial de la app —que vive en un
    backend con endpoints públicos sin sesión— no tiene que alcanzar para tocar la
    copia. El endpoint es configurable para poder mudar el destino a otra cuenta o a
    otro proveedor S3-compatible sin tocar este código.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_EVIDENCE_BACKUP_ENDPOINT_URL,
        aws_access_key_id=settings.R2_EVIDENCE_BACKUP_ACCESS_KEY,
        aws_secret_access_key=settings.R2_EVIDENCE_BACKUP_SECRET_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


# --- Keys -------------------------------------------------------------------


def backup_key_for(key):
    """Key del objeto en el bucket de respaldo.

    Por default es la MISMA key que en el principal: restaurar es copiar de vuelta sin
    traducir nada. El prefijo opcional existe para poder probar el circuito contra un
    bucket que ya existe sin mezclarse con su contenido.
    """
    prefix = settings.R2_EVIDENCE_BACKUP_PREFIX.strip("/")
    return f"{prefix}/{key}" if prefix else key


def key_from_file_url(url):
    """Key en el bucket a partir de `Evidence.file_url`. None si no se puede deducir.

    El camino normal es sacarle el prefijo público. El fallback por `/evidence/` cubre
    las filas viejas si `R2_PUBLIC_BASE_URL` cambia —está pendiente de la 2.4 pasar del
    dev URL `pub-….r2.dev` a un dominio propio—: sin él, el día del cambio la auditoría
    dejaría de reconocer TODAS las fotos ya guardadas.
    """
    base = settings.R2_PUBLIC_BASE_URL.rstrip("/") + "/"
    if url.startswith(base):
        return url[len(base):]

    marker = "/evidence/"
    position = url.find(marker)
    return url[position + 1:] if position != -1 else None


def referenced_keys():
    """Keys que alguna fila de Evidence dice tener. Es lo que la app promete que existe."""
    # Import local: este módulo lo importa el comando de backup, que tiene que poder
    # correr aunque la app de shipments cambie de forma.
    from shipments.models import Evidence

    keys = {}
    for pk, url in Evidence.objects.values_list("pk", "file_url"):
        key = key_from_file_url(url or "")
        if key:
            keys[key] = pk
    return keys


# --- Listados ---------------------------------------------------------------


def list_objects(client, bucket, prefix=""):
    """Todos los objetos del bucket como {key: {"size", "last_modified"}}."""
    objects = {}
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                objects[obj["Key"]] = {
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                }
    except (BotoCoreError, ClientError) as exc:
        raise EvidenceBackupError(f"No se pudo listar el bucket {bucket}: {exc}") from exc
    return objects


def list_source():
    return list_objects(get_source_client(), settings.R2_BUCKET_NAME)


def list_backup():
    prefix = settings.R2_EVIDENCE_BACKUP_PREFIX.strip("/")
    objects = list_objects(
        get_backup_client(),
        settings.R2_EVIDENCE_BACKUP_BUCKET_NAME,
        f"{prefix}/" if prefix else "",
    )
    if not prefix:
        return objects
    # Se devuelve indexado por la key ORIGINAL, para poder comparar contra el origen.
    cut = len(prefix) + 1
    return {key[cut:]: value for key, value in objects.items()}


# --- Copia ------------------------------------------------------------------


def copy_object(source_client, backup_client, key):
    """Copia UN objeto del bucket principal al de respaldo. Devuelve (bytes, sha256).

    Se baja y se sube en vez de usar `copy_object` de S3 porque son dos credenciales
    distintas: una copia del lado del servidor necesitaría un solo token con permiso
    sobre los dos buckets, y ese token —capaz de leer y borrar la evidencia Y su
    respaldo— es justamente lo que este diseño evita.

    El archivo se lee entero en memoria (la app limita las fotos a 15 MB y se copia de a
    una) para poder calcular el sha256 del contenido real que se sube y dejarlo en la
    metadata: sin él, más adelante no hay forma de probar que la copia es la foto.
    """
    try:
        obj = source_client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        body = obj["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        raise EvidenceBackupError(f"No se pudo leer {key} del bucket principal: {exc}") from exc

    digest = hashlib.sha256(body).hexdigest()
    extra = {
        "ContentType": obj.get("ContentType") or "application/octet-stream",
        "Metadata": {
            "sha256": digest,
            "source-bucket": settings.R2_BUCKET_NAME,
            "copied-at": datetime.now(dt_timezone.utc).isoformat(),
        },
    }

    destination = backup_key_for(key)
    try:
        backup_client.put_object(
            Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME,
            Key=destination,
            Body=body,
            **extra,
        )
        head = backup_client.head_object(
            Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=destination
        )
    except (BotoCoreError, ClientError) as exc:
        raise EvidenceBackupError(f"No se pudo copiar {key} al respaldo: {exc}") from exc

    # Confirmar contra el storage, no contra la respuesta de la subida: una copia
    # cortada deja un objeto de menos bytes, y ese es el que uno descubre roto el día
    # que hace falta.
    if head["ContentLength"] != len(body):
        raise EvidenceBackupError(
            f"La copia de {key} no coincide: {head['ContentLength']} bytes en el "
            f"respaldo contra {len(body)} en el principal."
        )
    return len(body), digest


def sync(*, dry_run=False, limit=None):
    """Copia al respaldo todo lo que esté en el bucket principal y falte en el otro.

    Incremental por diferencia de listados: las keys de evidencia son inmutables, así
    que una key que ya está en el destino con el mismo tamaño es la misma foto y no se
    vuelve a subir. Una key presente con OTRO tamaño sí se recopia: es una copia que
    quedó cortada.
    """
    source = list_source()
    backup = list_backup()

    pending = [
        key
        for key, data in sorted(source.items())
        if key not in backup or backup[key]["size"] != data["size"]
    ]
    result = {
        "source_total": len(source),
        "backup_total": len(backup),
        "pending": len(pending),
        "copied": 0,
        "copied_bytes": 0,
        "dry_run": dry_run,
        "keys": [],
    }
    if dry_run or not pending:
        result["keys"] = pending
        return result

    source_client = get_source_client()
    backup_client = get_backup_client()
    for key in pending[:limit] if limit else pending:
        size, _ = copy_object(source_client, backup_client, key)
        result["copied"] += 1
        result["copied_bytes"] += size
        result["keys"].append(key)
        logger.info("Evidencia respaldada: %s (%s bytes)", key, size)

    return result


# --- Auditoría --------------------------------------------------------------


def audit():
    """Estado de la copia. No modifica nada. Es lo que corre el cron de chequeo.

    Mira dos cosas distintas, y la segunda es la que de verdad importa:

    1. `sin_respaldo`: fotos del bucket principal que todavía no se copiaron y ya
       pasaron `EVIDENCE_BACKUP_MAX_AGE_HOURS`. Detecta que el job de copia se rompió o
       nunca se dio de alta. Las recientes no cuentan: es normal que estén esperando la
       próxima corrida.
    2. `perdidas`: keys que una fila de Evidence dice tener y que YA NO ESTÁN en el
       bucket principal. Eso es una foto perdida — la app nunca borra evidencia. De cada
       una se informa si el respaldo la tiene (recuperable) o no.

    Los objetos que están en el respaldo, ya no en el principal y tampoco los referencia
    ningún Evidence son borrados deliberados con su fila —la limpieza de los smoke
    tests, por ejemplo—: se informan, pero no son una falla.
    """
    now = datetime.now(dt_timezone.utc)
    cutoff = now - timedelta(hours=settings.EVIDENCE_BACKUP_MAX_AGE_HOURS)

    source = list_source()
    backup = list_backup()
    referenced = referenced_keys()

    sin_respaldo = sorted(
        key
        for key, data in source.items()
        if data["last_modified"] < cutoff
        and (key not in backup or backup[key]["size"] != data["size"])
    )
    esperando = sorted(key for key in source if key not in backup and key not in sin_respaldo)

    perdidas = [
        {
            "key": key,
            "evidence_id": evidence_id,
            "recuperable": key in backup,
        }
        for key, evidence_id in sorted(referenced.items())
        if key not in source
    ]

    return {
        "checked_at": now,
        "source_total": len(source),
        "backup_total": len(backup),
        "referenced_total": len(referenced),
        "sin_respaldo": sin_respaldo,
        "esperando": esperando,
        "perdidas": perdidas,
        "solo_en_respaldo": sorted(
            key for key in backup if key not in source and key not in referenced
        ),
        "ok": not sin_respaldo and not perdidas,
    }


# --- Restauración -----------------------------------------------------------


def restore_object(key):
    """Devuelve UNA foto del respaldo al bucket principal. Devuelve (bytes, sha256).

    No pisa: si la key ya existe en el principal, corta. Restaurar encima de un archivo
    que está es, o un error de tipeo, o una foto que en realidad no se había perdido.
    """
    source_client = get_source_client()
    backup_client = get_backup_client()

    try:
        source_client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
            raise EvidenceBackupError(
                f"No se pudo consultar {key} en el bucket principal: {exc}"
            ) from exc
    else:
        raise EvidenceBackupError(
            f"{key} YA existe en el bucket principal: no se pisa. Si de verdad querés "
            f"reemplazarlo, borralo primero a mano."
        )

    origin = backup_key_for(key)
    try:
        obj = backup_client.get_object(
            Bucket=settings.R2_EVIDENCE_BACKUP_BUCKET_NAME, Key=origin
        )
        body = obj["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        raise EvidenceBackupError(f"El respaldo no tiene {key}: {exc}") from exc

    digest = hashlib.sha256(body).hexdigest()
    stored = (obj.get("Metadata") or {}).get("sha256")
    if stored and stored != digest:
        raise EvidenceBackupError(
            f"La copia de {key} no coincide con su propio sha256 ({stored} guardado "
            f"contra {digest} calculado): el archivo del respaldo está corrupto."
        )

    try:
        source_client.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=obj.get("ContentType") or "application/octet-stream",
        )
        head = source_client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise EvidenceBackupError(f"No se pudo restaurar {key}: {exc}") from exc

    if head["ContentLength"] != len(body):
        raise EvidenceBackupError(
            f"La restauración de {key} quedó incompleta: {head['ContentLength']} bytes "
            f"contra {len(body)} del respaldo."
        )

    logger.info("Evidencia restaurada desde el respaldo: %s (%s bytes)", key, len(body))
    return len(body), digest
