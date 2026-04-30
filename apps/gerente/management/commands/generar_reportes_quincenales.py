"""
management/commands/generar_reportes_quincenales.py

Genera automáticamente el reporte quincenal y lo guarda en /media/reportes/.

Uso manual:
    python manage.py generar_reportes_quincenales

Configurar en cron (ejecutar días 1 y 16 de cada mes a las 02:00):
    0 2 1,16 * * /ruta/al/venv/bin/python /ruta/al/proyecto/manage.py generar_reportes_quincenales
"""
import os
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.gerente.models import Configuracion
from apps.gerente.reports import exportar_excel, exportar_pdf


class Command(BaseCommand):
    help = "Genera el reporte quincenal en Excel y PDF y lo guarda en /media/reportes/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fecha",
            type=str,
            default=None,
            help="Fecha de referencia para calcular la quincena anterior (YYYY-MM-DD). "
                 "Por defecto: hoy.",
        )
        parser.add_argument(
            "--solo-excel",
            action="store_true",
            default=False,
            help="Generar solo el archivo Excel (sin PDF).",
        )

    def handle(self, *args, **options):
        # ── Calcular el rango de la quincena anterior ─────────────────────────
        if options["fecha"]:
            hoy = date.fromisoformat(options["fecha"])
        else:
            hoy = timezone.now().date()

        if hoy.day >= 16:
            # Segunda quincena del mes anterior: del 1 al 15
            desde = date(hoy.year, hoy.month, 1)
            hasta = date(hoy.year, hoy.month, 15)
        else:
            # Primera quincena del mes pasado: del 16 al fin de mes
            primer_dia_mes_actual = date(hoy.year, hoy.month, 1)
            ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
            desde = date(ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month, 16)
            hasta = ultimo_dia_mes_anterior

        self.stdout.write(f"Generando reporte quincenal: {desde} → {hasta}")

        # ── Directorio de destino ─────────────────────────────────────────────
        media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
        reportes_dir = media_root / "reportes"
        reportes_dir.mkdir(parents=True, exist_ok=True)

        tag = f"{desde.strftime('%Y-%m-%d')}_{hasta.strftime('%Y-%m-%d')}"

        archivos_generados = []

        # ── Generar Excel ────────────────────────────────────────────────────
        try:
            xlsx_path = reportes_dir / f"reporte_quincenal_{tag}.xlsx"
            xlsx_bytes = exportar_excel(desde, hasta)
            xlsx_path.write_bytes(xlsx_bytes)
            archivos_generados.append(str(xlsx_path))
            self.stdout.write(self.style.SUCCESS(f"  ✓ Excel: {xlsx_path}"))
        except ImportError:
            self.stderr.write("  ✗ openpyxl no instalado. Omitiendo Excel.")
        except Exception as e:
            self.stderr.write(f"  ✗ Error generando Excel: {e}")

        # ── Generar PDF ───────────────────────────────────────────────────────
        if not options["solo_excel"]:
            try:
                pdf_path = reportes_dir / f"reporte_quincenal_{tag}.pdf"
                pdf_bytes = exportar_pdf(desde, hasta)
                pdf_path.write_bytes(pdf_bytes)
                archivos_generados.append(str(pdf_path))
                self.stdout.write(self.style.SUCCESS(f"  ✓ PDF:   {pdf_path}"))
            except ImportError:
                self.stderr.write("  ✗ weasyprint no instalado. Omitiendo PDF.")
            except Exception as e:
                self.stderr.write(f"  ✗ Error generando PDF: {e}")

        # ── Registrar en BD (usando Configuracion como log simple) ─────────────
        if archivos_generados:
            Configuracion.objects.update_or_create(
                clave=f"reporte_quincenal_{tag}",
                defaults={"valor": "|".join(archivos_generados)},
            )
            self.stdout.write(self.style.SUCCESS(
                f"\nReporte quincenal {tag} generado correctamente."
            ))
        else:
            self.stderr.write("\nNo se pudo generar ningún archivo.")
