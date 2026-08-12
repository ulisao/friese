"""Respaldo de las fotos de evidencia en un segundo bucket (tarea 7.2).

Corre como cron en Railway (`railway.cron-evidence-backup.json`) y también a mano:

    python manage.py backup_evidence                  # copia lo que falte al respaldo
    python manage.py backup_evidence --dry-run        # dice qué copiaría, sin copiar
    python manage.py backup_evidence --check-only     # audita, no copia nada
    python manage.py backup_evidence --restore KEY    # devuelve UNA foto al principal
    python manage.py backup_evidence --restore-missing  # devuelve TODAS las perdidas

El backup de la base (7.1) guarda las URLs de las fotos, no los bytes: sin esto, una
base restaurada apunta a archivos que ya no existen. El procedimiento de recuperación
está en `BACKUP.md`, sección 7.

Exit code 0 si todo quedó bien; != 0 en cualquier otro caso, para que la corrida figure
fallada en Railway. Además se manda un email a `BACKUP_ALERT_EMAIL`.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ops.alerts import send_ops_alert
from ops.evidence_backup import audit, restore_object, sync

logger = logging.getLogger(__name__)


def _mb(num_bytes):
    return f"{num_bytes / 1024 / 1024:.2f} MB"


class Command(BaseCommand):
    help = (
        "Copia al bucket de respaldo las fotos de evidencia que le falten. Con "
        "--check-only solo audita, y con --restore devuelve una foto al bucket principal."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="No copia: audita el respaldo y avisa si falta algo o si se perdió una foto.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista lo que habría que copiar, sin copiar nada.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Copia como mucho N objetos en esta corrida.",
        )
        parser.add_argument(
            "--restore",
            metavar="KEY",
            help="Restaura esa key del respaldo al bucket principal (no pisa si existe).",
        )
        parser.add_argument(
            "--restore-missing",
            action="store_true",
            help="Restaura todas las fotos que un Evidence referencia y ya no están.",
        )

    def handle(self, *args, **options):
        if options["restore"]:
            return self._restore_one(options["restore"])
        if options["restore_missing"]:
            return self._restore_missing()
        if options["check_only"]:
            return self._check_only()
        return self._sync(dry_run=options["dry_run"], limit=options["limit"])

    # --- Copia --------------------------------------------------------------

    def _sync(self, *, dry_run, limit):
        try:
            result = sync(dry_run=dry_run, limit=limit)
        # Ancho a propósito, igual que en backup_database: cualquier falla tiene que
        # avisar. Un respaldo que se rompe en silencio es lo que esta tarea evita.
        except Exception as exc:  # noqa: BLE001
            self._fail(
                "Falló el respaldo de las fotos de evidencia",
                f"La copia de las fotos de evidencia al bucket de respaldo NO se pudo "
                f"completar.\n\nError:\n{exc}\n\nMientras esto siga fallando, las fotos "
                f"nuevas quedan sin copia: si se pierde el bucket principal "
                f"({settings.R2_BUCKET_NAME}), esas fotos no se recuperan.\n\n"
                f"Ver BACKUP.md, sección 7.",
                exc,
            )

        self.stdout.write(
            f"Bucket principal: {result['source_total']} objeto(s). "
            f"Respaldo: {result['backup_total']}."
        )
        if result["dry_run"]:
            self.stdout.write(f"Habría que copiar {result['pending']} objeto(s):")
            for key in result["keys"][:50]:
                self.stdout.write(f"  {key}")
            if result["pending"] > 50:
                self.stdout.write(f"  … y {result['pending'] - 50} más")
            return

        if not result["copied"]:
            self.stdout.write(self.style.SUCCESS("El respaldo ya estaba al día."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Copiadas {result['copied']} foto(s) "
                f"({_mb(result['copied_bytes'])}) a "
                f"r2://{settings.R2_EVIDENCE_BACKUP_BUCKET_NAME}."
            )
        )
        if result["pending"] > result["copied"]:
            self.stdout.write(
                f"Quedan {result['pending'] - result['copied']} para la próxima corrida "
                f"(--limit)."
            )

    # --- Auditoría ----------------------------------------------------------

    def _check_only(self):
        try:
            report = audit()
        except Exception as exc:  # noqa: BLE001 — ver el comentario de _sync
            self._fail(
                "No se pudo auditar el respaldo de las fotos",
                f"El chequeo del respaldo de evidencia no pudo leer los buckets.\n\n"
                f"Error:\n{exc}",
                exc,
            )

        summary = (
            f"Principal: {report['source_total']} foto(s). "
            f"Respaldo: {report['backup_total']}. "
            f"Referenciadas por un Evidence: {report['referenced_total']}."
        )
        self.stdout.write(summary)
        if report["esperando"]:
            self.stdout.write(
                f"  {len(report['esperando'])} foto(s) recientes esperando la próxima "
                f"corrida (normal)."
            )
        if report["solo_en_respaldo"]:
            self.stdout.write(
                f"  {len(report['solo_en_respaldo'])} objeto(s) solo en el respaldo, sin "
                f"Evidence que los referencie (borrados a propósito con su fila)."
            )

        problemas = []
        if report["perdidas"]:
            recuperables = [p for p in report["perdidas"] if p["recuperable"]]
            perdidas_del_todo = [p for p in report["perdidas"] if not p["recuperable"]]
            detalle = "\n".join(
                f"  - {p['key']} (Evidence #{p['evidence_id']}) — "
                f"{'está en el respaldo' if p['recuperable'] else 'NO está en el respaldo'}"
                for p in report["perdidas"][:50]
            )
            problemas.append(
                f"{len(report['perdidas'])} foto(s) que la base dice tener YA NO ESTÁN "
                f"en el bucket principal ({settings.R2_BUCKET_NAME}). La aplicación "
                f"nunca borra evidencia, así que esto es un borrado por error o algo "
                f"peor.\n"
                f"{len(recuperables)} se pueden recuperar del respaldo con:\n"
                f"    python manage.py backup_evidence --restore-missing\n"
                f"{len(perdidas_del_todo)} NO están en el respaldo.\n\n{detalle}"
            )
        if report["sin_respaldo"]:
            problemas.append(
                f"{len(report['sin_respaldo'])} foto(s) de más de "
                f"{settings.EVIDENCE_BACKUP_MAX_AGE_HOURS}hs siguen sin copia en el "
                f"respaldo. Lo más probable es que el cron de copia esté fallando o no "
                f"esté dado de alta. Revisar sus últimas ejecuciones en Railway.\n\n"
                + "\n".join(f"  - {key}" for key in report["sin_respaldo"][:50])
            )

        if problemas:
            self._fail(
                "Problemas con las fotos de evidencia",
                f"{summary}\n\n" + "\n\n".join(problemas) + "\n\nVer BACKUP.md, sección 7.",
                None,
            )

        self.stdout.write(self.style.SUCCESS("Respaldo de evidencia al día."))

    # --- Restauración -------------------------------------------------------

    def _restore_one(self, key):
        try:
            size, digest = restore_object(key)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Restaurada {key} ({_mb(size)}) en r2://{settings.R2_BUCKET_NAME}."
            )
        )
        self.stdout.write(f"  sha256: {digest}")

    def _restore_missing(self):
        report = audit()
        recuperables = [p["key"] for p in report["perdidas"] if p["recuperable"]]
        if not report["perdidas"]:
            self.stdout.write(self.style.SUCCESS("No falta ninguna foto en el principal."))
            return

        perdidas_del_todo = [p["key"] for p in report["perdidas"] if not p["recuperable"]]
        for key in recuperables:
            size, _ = restore_object(key)
            self.stdout.write(f"  restaurada {key} ({_mb(size)})")

        self.stdout.write(
            self.style.SUCCESS(f"Restauradas {len(recuperables)} foto(s) del respaldo.")
        )
        if perdidas_del_todo:
            # No se puede hacer nada más desde acá, pero tiene que quedar dicho: son
            # fotos que la base promete y que ya no existen en ninguna parte.
            self.stdout.write(
                self.style.ERROR(
                    f"{len(perdidas_del_todo)} foto(s) NO están tampoco en el respaldo:"
                )
            )
            for key in perdidas_del_todo:
                self.stdout.write(f"  {key}")
            raise CommandError(
                f"{len(perdidas_del_todo)} foto(s) no se pudieron recuperar."
            )

    # --- Falla --------------------------------------------------------------

    def _fail(self, subject, body, exc):
        """Loguea, avisa por email y corta con exit code != 0."""
        logger.error("Respaldo de evidencia: %s. %s", subject, body)
        send_ops_alert(f"[Friese] {subject}", body)
        raise CommandError(subject) from exc
