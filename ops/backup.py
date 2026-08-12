"""Backup de la base de datos a Cloudflare R2 (tarea 7.1).

El plan de Supabase del proyecto es el FREE, que no incluye backups gestionados ni
point-in-time-recovery: si la base se pierde o alguien borra datos por error, no hay
nada que restaurar del lado de Supabase. Este módulo es esa red, y hoy es la única.

Todo el conocimiento del backup vive acá (igual que `shipments/storage.py` concentra
el de R2): armar el dump, verificarlo, subirlo, podar los viejos y auditar que el más
nuevo no esté vencido. El management command `backup_database` solo orquesta.

El procedimiento de restauración está en `BACKUP.md`, en la raíz del repo.
"""

import gzip
import hashlib
import logging
import os
import re
import subprocess
import tempfile
import zlib
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

# Última línea que escribe pg_dump cuando terminó de verdad. Es la verificación más
# importante del dump: un archivo cortado a la mitad (red caída, disco lleno, proceso
# matado) no la tiene, y sin ella un backup puede verse "subido y con peso" pero estar
# incompleto. Se chequea junto con el exit code, no en su lugar.
DUMP_COMPLETE_MARKER = "-- PostgreSQL database dump complete"

# Puertos del pooler de Supabase (Supavisor).
SUPABASE_TRANSACTION_PORT = 6543
SUPABASE_SESSION_PORT = 5432


class BackupError(RuntimeError):
    """Falló alguna etapa del backup. El comando la traduce a un exit code != 0."""


# --- Conexión ---------------------------------------------------------------


def build_backup_dsn(database_url):
    """DSN a usar para el dump, a partir del `DATABASE_URL` de la app.

    La app se conecta por el pooler de Supabase en modo TRANSACCIÓN (puerto 6543),
    que multiplexa varias conexiones lógicas sobre una física. pg_dump no puede
    trabajar así: necesita una sesión propia y estable para sostener el snapshot
    (`SET TRANSACTION SNAPSHOT`, cursores, `search_path`). El mismo pooler expone el
    modo SESIÓN en el 5432, que sí sirve, con las mismas credenciales.

    Por eso el default es "el DATABASE_URL de la app con el puerto cambiado". Si algún
    día la conexión cambia de forma, se sobreescribe entero con `BACKUP_DATABASE_URL`.
    """
    parts = urlsplit(database_url)
    if parts.port != SUPABASE_TRANSACTION_PORT:
        return database_url

    host = parts.hostname or ""
    userinfo = parts.netloc.rsplit("@", 1)[0] if "@" in parts.netloc else ""
    hostport = f"{host}:{SUPABASE_SESSION_PORT}"
    netloc = f"{userinfo}@{hostport}" if userinfo else hostport
    return parts._replace(netloc=netloc).geturl()


def backup_dsn():
    """Conexión efectiva del backup: la explícita del env, o la derivada de la app."""
    return settings.BACKUP_DATABASE_URL or build_backup_dsn(settings.DATABASE_URL)


def _pg_connection_args(dsn):
    """Flags y entorno para pg_dump, a partir del DSN.

    La contraseña va por `PGPASSWORD` y NO en la línea de comandos: los argumentos de
    un proceso los puede leer cualquiera que corra `ps` en la misma máquina.
    """
    parts = urlsplit(dsn)
    if not parts.hostname:
        raise BackupError(f"DSN de backup inválido, no tiene host: {dsn!r}")

    args = [
        "--host", parts.hostname,
        "--port", str(parts.port or SUPABASE_SESSION_PORT),
        "--dbname", (parts.path or "/postgres").lstrip("/") or "postgres",
    ]
    if parts.username:
        args += ["--username", parts.username]

    # Supabase solo acepta TLS. Se respeta un sslmode explícito del DSN por si algún
    # día el destino es otro (ej. un Postgres local sin TLS en una prueba).
    sslmode = parse_qs(parts.query).get("sslmode", ["require"])[0]
    env = {**os.environ, "PGSSLMODE": sslmode}
    if parts.password:
        env["PGPASSWORD"] = parts.password
    # pg_dump no debe quedarse colgado si el pooler deja de responder: sin esto, el
    # cron podría quedar corriendo hasta que la plataforma lo mate, sin dejar rastro.
    env["PGCONNECT_TIMEOUT"] = str(settings.BACKUP_CONNECT_TIMEOUT_SECONDS)
    return args, env


# --- Dump -------------------------------------------------------------------


def _expected_tables():
    """Tablas que la base tiene AHORA, según Django. Es contra esto que se verifica."""
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def run_pg_dump(dsn, destination):
    """Corre pg_dump y deja el resultado comprimido en `destination` (.sql.gz).

    Solo se dumpea el esquema `public`, que es el que la aplicación posee: los
    esquemas `auth`, `storage`, `realtime` y `vault` son internos de Supabase, el rol
    de la app no tiene permisos completos sobre ellos (no es superusuario) y el
    proyecto no los usa — la autenticación es la de Django, en `public.users_user`.

    `--no-owner` y `--no-privileges` sacan los OWNER y los GRANT: los roles de
    Supabase (`anon`, `authenticated`, `service_role`) no existen en un Postgres
    cualquiera, y con ellos adentro el dump solo se podría restaurar en otro Supabase.
    Django se conecta con un único rol, así que no necesita esos permisos.

    Devuelve (bytes del dump sin comprimir, sha256 del dump sin comprimir).
    """
    args, env = _pg_connection_args(dsn)
    cmd = [
        settings.PG_DUMP_PATH,
        *args,
        "--schema", "public",
        "--format", "plain",
        "--encoding", "UTF8",
        "--no-owner",
        "--no-privileges",
    ]

    digest = hashlib.sha256()
    raw_bytes = 0

    # stderr va a un archivo y no a un PIPE a propósito: leyendo stdout hasta el final
    # antes de tocar stderr, un error largo de pg_dump podría llenar el buffer del pipe
    # y dejar los dos procesos esperándose (deadlock clásico).
    with tempfile.TemporaryFile() as stderr_file:
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=stderr_file, env=env
            )
        except OSError as exc:
            # El caso típico: pg_dump no está instalado en la imagen. Se traduce a
            # BackupError para que salga por el aviso y no como un traceback pelado.
            raise BackupError(
                f"No se pudo ejecutar pg_dump en {settings.PG_DUMP_PATH!r}: {exc}. "
                "Revisá PG_DUMP_PATH y que el paquete postgresql esté en la imagen "
                "(ver nixpacks.toml)."
            ) from exc
        try:
            with gzip.open(destination, "wb", compresslevel=6) as gz:
                while True:
                    chunk = proc.stdout.read(1024 * 256)
                    if not chunk:
                        break
                    raw_bytes += len(chunk)
                    digest.update(chunk)
                    gz.write(chunk)
        finally:
            proc.stdout.close()
            returncode = proc.wait()

        stderr_file.seek(0)
        stderr = stderr_file.read().decode("utf-8", "replace").strip()

    if returncode != 0:
        raise BackupError(
            f"pg_dump falló con exit code {returncode}. Salida de error:\n{stderr}"
        )
    if stderr:
        # pg_dump escribe avisos por stderr sin que eso sea una falla (ej. permisos
        # sobre un objeto que no se dumpea). Quedan en el log, pero no cortan.
        logger.warning("pg_dump terminó OK pero escribió avisos:\n%s", stderr)

    return raw_bytes, digest.hexdigest()


# --- Verificación del dump --------------------------------------------------

_CREATE_TABLE_RE = re.compile(r'^CREATE TABLE (?:ONLY )?public\."?([A-Za-z0-9_]+)"?')
_COPY_RE = re.compile(r'^COPY public\."?([A-Za-z0-9_]+)"?.*FROM stdin;$')


def verify_dump(path, expected_tables):
    """Abre el .sql.gz recién escrito y confirma que sirve. Devuelve el detalle.

    Un backup que no se verificó es una suposición. Se chequea, en orden:
      1. que el gzip se descomprima entero (detecta corrupción y truncado);
      2. que esté la línea final de pg_dump (detecta un dump cortado a la mitad, que
         es la falla que más fácil pasa desapercibida: pesa, se sube, y no sirve);
      3. que TODAS las tablas que la base tiene hoy estén en el dump (detecta un
         `--schema` mal puesto o una tabla nueva que se quedó afuera);
      4. cuántas filas trae cada tabla, que es lo que después se compara contra la
         base restaurada.

    Se lee línea por línea y no de una: el dump entero en memoria hoy son 130 KB, pero
    crece con la base, y este código corre en un contenedor chico.

    Llevar el estado de "estoy adentro de un bloque COPY" no es solo para contar: los
    datos de una tabla pueden contener una línea que empiece con `CREATE TABLE public.`
    (un nombre de producto, el motivo de una queja), y buscando por patrón suelto esa
    fila se contaría como una tabla del esquema.
    """
    dumped_tables = set()
    rows_by_table = {}
    complete = False
    in_copy = None

    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as gz:
            for line in gz:
                line = line.rstrip("\n")
                if in_copy is not None:
                    # Dentro de un COPY, `\.` en su propia línea cierra el bloque.
                    if line == "\\.":
                        in_copy = None
                    else:
                        rows_by_table[in_copy] += 1
                    continue

                if line.startswith("COPY public."):
                    match = _COPY_RE.match(line)
                    if match:
                        in_copy = match.group(1)
                        rows_by_table.setdefault(in_copy, 0)
                elif line.startswith("CREATE TABLE "):
                    match = _CREATE_TABLE_RE.match(line)
                    if match:
                        dumped_tables.add(match.group(1))
                elif line.startswith(DUMP_COMPLETE_MARKER):
                    complete = True
    # `zlib.error` va aparte porque NO hereda de OSError: un gzip corrupto a mitad de
    # archivo sale por ahí, no por `gzip.BadGzipFile`.
    except (OSError, EOFError, zlib.error) as exc:
        raise BackupError(f"El dump comprimido no se puede leer: {exc}") from exc

    if in_copy is not None:
        raise BackupError(
            f"El dump está cortado en medio de los datos de la tabla {in_copy!r}."
        )
    if not complete:
        raise BackupError(
            "El dump está incompleto: no tiene la línea final de pg_dump "
            f"({DUMP_COMPLETE_MARKER!r}). El archivo se descarta."
        )

    missing = sorted(expected_tables - dumped_tables)
    if missing:
        raise BackupError(
            "El dump no incluye tablas que la base sí tiene: " + ", ".join(missing)
        )

    return {"tables": len(dumped_tables), "rows_by_table": rows_by_table}


# --- R2 ---------------------------------------------------------------------


def get_backup_client():
    """Cliente boto3 del bucket de BACKUPS.

    Es un bucket y un token aparte del de las fotos de evidencia: si se filtra la
    credencial de la app (que sube evidencia desde un endpoint público), no alcanza
    para borrar los backups. Las claves caen a las de la app solo para poder probar
    en desarrollo sin configurar un segundo token.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_BACKUP_ACCESS_KEY,
        aws_secret_access_key=settings.R2_BACKUP_SECRET_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def build_backup_key(moment):
    """Key del objeto en el bucket, ordenable por nombre y agrupada por mes.

    El timestamp va en UTC y en formato ISO compacto para que el orden alfabético de
    la lista sea el orden cronológico: así encontrar el último backup es mirar el
    final de la lista, sin depender de la fecha que reporte el storage.
    """
    prefix = settings.R2_BACKUP_PREFIX.strip("/")
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}/{moment:%Y/%m}/friese-db-{stamp}.sql.gz"


def upload_backup(client, path, key, metadata):
    """Sube el dump y confirma contra el storage que llegó entero.

    El `head_object` posterior no es paranoia: una subida cortada puede dejar un
    objeto de menos bytes, y ese es exactamente el backup que uno descubre roto el día
    que lo necesita.
    """
    local_size = path.stat().st_size
    try:
        client.upload_file(
            str(path),
            settings.R2_BACKUP_BUCKET_NAME,
            key,
            ExtraArgs={
                "ContentType": "application/gzip",
                "Metadata": metadata,
            },
        )
        head = client.head_object(Bucket=settings.R2_BACKUP_BUCKET_NAME, Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise BackupError(f"No se pudo subir el backup a R2 ({key}): {exc}") from exc

    remote_size = head["ContentLength"]
    if remote_size != local_size:
        raise BackupError(
            f"El backup subido no coincide con el local: {remote_size} bytes en R2 "
            f"contra {local_size} locales ({key})."
        )
    return remote_size


def list_backups(client):
    """Todos los backups del bucket, del más viejo al más nuevo."""
    prefix = settings.R2_BACKUP_PREFIX.strip("/") + "/"
    objects = []
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=settings.R2_BACKUP_BUCKET_NAME, Prefix=prefix
        ):
            objects.extend(page.get("Contents", []))
    except (BotoCoreError, ClientError) as exc:
        raise BackupError(f"No se pudo listar el bucket de backups: {exc}") from exc

    return sorted(objects, key=lambda obj: obj["LastModified"])


def prune_backups(client, backups, now):
    """Borra los backups vencidos. Devuelve las keys borradas.

    Dos frenos, porque este es el único código del proyecto que borra backups:
    nunca baja de `BACKUP_MIN_KEEP` copias, aunque todas estén vencidas, y nunca toca
    las más nuevas. Si el cron estuvo caído dos meses, la poda no deja el bucket vacío.
    """
    retention = settings.BACKUP_RETENTION_DAYS
    keep = settings.BACKUP_MIN_KEEP
    if retention <= 0 or len(backups) <= keep:
        return []

    cutoff = now - timedelta(days=retention)
    # `backups` viene del más viejo al más nuevo: los candidatos son los primeros,
    # dejando siempre las `keep` últimas fuera de la poda.
    candidates = backups[: len(backups) - keep]
    expired = [obj for obj in candidates if obj["LastModified"] < cutoff]
    if not expired:
        return []

    keys = [obj["Key"] for obj in expired]
    try:
        # delete_objects acepta hasta 1000 keys por llamada.
        for start in range(0, len(keys), 1000):
            client.delete_objects(
                Bucket=settings.R2_BACKUP_BUCKET_NAME,
                Delete={"Objects": [{"Key": k} for k in keys[start : start + 1000]]},
            )
    except (BotoCoreError, ClientError) as exc:
        raise BackupError(f"No se pudieron borrar los backups vencidos: {exc}") from exc

    return keys


def check_freshness(backups, now):
    """Antigüedad del backup más nuevo. Es el criterio de aceptación de la tarea.

    Devuelve (ok, horas, objeto). `ok` es False si no hay ningún backup o si el más
    nuevo pasó `BACKUP_MAX_AGE_HOURS`.
    """
    if not backups:
        return False, None, None

    newest = backups[-1]
    age_hours = (now - newest["LastModified"]).total_seconds() / 3600
    return age_hours <= settings.BACKUP_MAX_AGE_HOURS, age_hours, newest


# --- Orquestación -----------------------------------------------------------


def create_backup(*, upload=True, keep_local=None):
    """Hace el backup completo: dump → verificación → subida → poda → auditoría.

    Devuelve un dict con el detalle de lo que pasó, para que el comando lo imprima y
    lo mande por email si hubo que avisar.
    """
    now = datetime.now(dt_timezone.utc)
    dsn = backup_dsn()
    expected = _expected_tables()

    tmp_dir = Path(keep_local) if keep_local else Path(tempfile.mkdtemp(prefix="friese-backup-"))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    key = build_backup_key(now)
    path = tmp_dir / Path(key).name

    logger.info("Backup: arrancando el dump de %s", urlsplit(dsn).hostname)
    raw_bytes, sha256 = run_pg_dump(dsn, path)
    detail = verify_dump(path, expected)
    gz_bytes = path.stat().st_size

    result = {
        "key": key,
        "created_at": now,
        "raw_bytes": raw_bytes,
        "gz_bytes": gz_bytes,
        "sha256": sha256,
        "local_path": path,
        "uploaded": False,
        "pruned": [],
        "fresh": None,
        "age_hours": None,
        **detail,
    }

    if not upload:
        logger.info("Backup: --no-upload, el dump queda solo en %s", path)
        return result

    client = get_backup_client()
    upload_backup(
        client,
        path,
        key,
        {
            "sha256": sha256,
            "raw-bytes": str(raw_bytes),
            "tables": str(detail["tables"]),
            "rows": str(sum(detail["rows_by_table"].values())),
            "created-at": now.isoformat(),
            "django-env": settings.DJANGO_ENV,
        },
    )
    result["uploaded"] = True
    logger.info("Backup: subido %s (%s bytes comprimidos)", key, gz_bytes)

    backups = list_backups(client)
    result["pruned"] = prune_backups(client, backups, now)
    if result["pruned"]:
        backups = [obj for obj in backups if obj["Key"] not in set(result["pruned"])]
    result["total_backups"] = len(backups)
    fresh, age_hours, _ = check_freshness(backups, now)
    result["fresh"], result["age_hours"] = fresh, age_hours

    if not keep_local:
        path.unlink(missing_ok=True)
        result["local_path"] = None
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    return result


def audit_backups():
    """Solo audita: ¿hay un backup y es más nuevo que `BACKUP_MAX_AGE_HOURS`?

    No dumpea ni sube nada. Es lo que corre el chequeo periódico para que una falla
    silenciosa del cron no pase inadvertida durante días.
    """
    now = datetime.now(dt_timezone.utc)
    backups = list_backups(get_backup_client())
    fresh, age_hours, newest = check_freshness(backups, now)
    return {
        "fresh": fresh,
        "age_hours": age_hours,
        "newest": newest,
        "total_backups": len(backups),
        "checked_at": now,
    }
