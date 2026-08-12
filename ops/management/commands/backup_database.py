"""Backup automático de la base a Cloudflare R2 (tarea 7.1).

Se corre como cron en Railway (ver `railway.cron-backup.json`) y también a mano:

    python manage.py backup_database              # dump + verificación + subida + poda
    python manage.py backup_database --check-only  # solo audita la antigüedad del último
    python manage.py backup_database --no-upload --keep-local ./tmp   # dump local

El plan de Supabase del proyecto es el FREE, que NO tiene backups gestionados: este
comando es la única copia que existe. El procedimiento de restauración está en
`BACKUP.md`, en la raíz del repo.

Exit code 0 si el backup quedó hecho y verificado; != 0 en cualquier otro caso, para
que la ejecución figure como fallida en la plataforma. Además se manda un email a
`BACKUP_ALERT_EMAIL`: sin aviso, un cron que se rompe pasa inadvertido justo hasta el
día que hay que restaurar.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ops.alerts import send_ops_alert
from ops.backup import audit_backups, create_backup

logger = logging.getLogger(__name__)


def _mb(num_bytes):
    return f"{num_bytes / 1024 / 1024:.2f} MB"


class Command(BaseCommand):
    help = (
        "Hace un dump de la base, lo verifica y lo sube al bucket de backups en R2. "
        "Con --check-only solo revisa que el último backup no esté vencido."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="No dumpea ni sube: solo audita la antigüedad del último backup.",
        )
        parser.add_argument(
            "--no-upload",
            action="store_true",
            help="Hace el dump y lo verifica, pero no lo sube a R2 (para probar).",
        )
        parser.add_argument(
            "--keep-local",
            metavar="DIR",
            help="Deja el .sql.gz en ese directorio en vez de borrarlo al terminar.",
        )

    def handle(self, *args, **options):
        if options["check_only"]:
            return self._check_only()
        return self._backup(
            upload=not options["no_upload"], keep_local=options["keep_local"]
        )

    # --- Backup -------------------------------------------------------------

    def _backup(self, *, upload, keep_local):
        try:
            result = create_backup(upload=upload, keep_local=keep_local)
        # Ancho a propósito: `BackupError` cubre las fallas previstas, pero cualquier
        # otra (disco lleno, la red que se corta, un bug acá) también tiene que avisar.
        # Un backup que se rompe en silencio es exactamente lo que esta tarea evita.
        except Exception as exc:  # noqa: BLE001
            self._fail(
                "Falló el backup de la base",
                f"El backup automático de la base de datos NO se pudo completar.\n\n"
                f"Error:\n{exc}\n\n"
                f"Mientras esto siga fallando, la base no tiene ninguna copia nueva. "
                f"El plan de Supabase es el Free, que no hace backups por su cuenta.\n\n"
                f"Cómo restaurar y cómo diagnosticar: BACKUP.md, en la raíz del repo.",
                exc,
            )

        rows = sum(result["rows_by_table"].values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Dump OK: {result['tables']} tablas, {rows} filas, "
                f"{_mb(result['raw_bytes'])} sin comprimir -> "
                f"{_mb(result['gz_bytes'])} comprimidos."
            )
        )
        self.stdout.write(f"  sha256: {result['sha256']}")

        if not result["uploaded"]:
            self.stdout.write(f"  archivo local: {result['local_path']}")
            self.stdout.write("No se subió a R2 (--no-upload).")
            return

        self.stdout.write(
            f"  subido a r2://{settings.R2_BACKUP_BUCKET_NAME}/{result['key']}"
        )
        if result["pruned"]:
            self.stdout.write(
                f"  podados {len(result['pruned'])} backup(s) de más de "
                f"{settings.BACKUP_RETENTION_DAYS} días."
            )
        self.stdout.write(
            f"  quedan {result['total_backups']} backup(s) en el bucket."
        )

        logger.info(
            "Backup de la base completado: %s (%s tablas, %s filas, %s bytes).",
            result["key"],
            result["tables"],
            rows,
            result["gz_bytes"],
        )
        # El backup recién subido tiene 0 horas, así que esto solo puede fallar si el
        # storage devuelve una fecha absurda. Se chequea igual: es el criterio de
        # aceptación de la tarea y no cuesta nada confirmarlo contra el bucket real.
        if result["fresh"] is False:
            self._fail(
                "El backup se subió pero el bucket no lo reporta como reciente",
                f"El backup {result['key']} se subió a R2, pero al listar el bucket el "
                f"más nuevo figura con {result['age_hours']:.1f} horas de antigüedad, "
                f"por encima del límite de {settings.BACKUP_MAX_AGE_HOURS}h.\n\n"
                f"Revisar el reloj del contenedor y el bucket.",
                None,
            )

    # --- Auditoría ----------------------------------------------------------

    def _check_only(self):
        try:
            report = audit_backups()
        except Exception as exc:  # noqa: BLE001 — ver el comentario de _backup
            self._fail(
                "No se pudo auditar el backup de la base",
                f"El chequeo de antigüedad del backup no pudo leer el bucket.\n\n"
                f"Error:\n{exc}",
                exc,
            )

        if report["newest"] is None:
            self._fail(
                "No hay ningún backup de la base",
                f"El bucket r2://{settings.R2_BACKUP_BUCKET_NAME}/"
                f"{settings.R2_BACKUP_PREFIX} está vacío: la base NO tiene ninguna "
                f"copia. El plan de Supabase es el Free, que no hace backups por su "
                f"cuenta.\n\nVer BACKUP.md.",
                None,
            )

        age = report["age_hours"]
        summary = (
            f"Último backup: {report['newest']['Key']} "
            f"({age:.1f}h, {_mb(report['newest']['Size'])}). "
            f"{report['total_backups']} backup(s) en el bucket."
        )

        if not report["fresh"]:
            self._fail(
                f"El backup de la base está vencido ({age:.0f}h)",
                f"El backup más nuevo de la base tiene {age:.1f} horas, por encima "
                f"del límite de {settings.BACKUP_MAX_AGE_HOURS}h.\n\n"
                f"{summary}\n\n"
                f"Lo más probable es que el cron de backup esté fallando. Revisar sus "
                f"últimas ejecuciones en Railway.",
                None,
            )

        self.stdout.write(self.style.SUCCESS(summary))

    # --- Falla --------------------------------------------------------------

    def _fail(self, subject, body, exc):
        """Loguea, avisa por email y corta con exit code != 0."""
        logger.error("Backup de la base: %s. %s", subject, body)
        send_ops_alert(f"[Friese] {subject}", body)
        raise CommandError(subject) from exc
