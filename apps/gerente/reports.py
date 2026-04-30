"""
gerente/reports.py
Lógica de generación de reportes en Excel y PDF para Mochi Matcha.

Dependencias requeridas (añadir a requirements.txt):
    openpyxl==3.1.2
    weasyprint==62.3
"""
from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from django.db.models import Sum, Count, DecimalField
from django.db.models.functions import TruncDate, Coalesce
from django.template.loader import render_to_string
from django.utils import timezone

from apps.pedidos.models import Pedido, DetallePedido


def _make_naive(dt):
    """Convierte un datetime aware a naive (local) para openpyxl, que no soporta tzinfo."""
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        return timezone.localtime(dt).replace(tzinfo=None)
    return dt


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de datos
# ──────────────────────────────────────────────────────────────────────────────

def _pedidos_periodo(desde: date, hasta: date):
    """Devuelve queryset de pedidos no cancelados en el rango [desde, hasta]."""
    return (
        Pedido.objects
        .filter(fecha_hora_ingreso__date__gte=desde, fecha_hora_ingreso__date__lte=hasta)
        .exclude(estado="cancelado")
        .prefetch_related("detalles__producto")
        .select_related("sesion__mesa")
    )


def _ventas_por_dia(pedidos):
    return list(
        pedidos
        .annotate(fecha=TruncDate("fecha_hora_ingreso"))
        .values("fecha")
        .annotate(
            total=Coalesce(
            Sum("detalles__subtotal_calculado"),
            Decimal("0.00"),
            output_field=DecimalField()
        ),
            tickets=Count("id", distinct=True),
        )
        .order_by("fecha")
    )


def _top_productos(desde: date, hasta: date, limit: int = 20):
    return list(
        DetallePedido.objects
        .filter(pedido__fecha_hora_ingreso__date__gte=desde,
                pedido__fecha_hora_ingreso__date__lte=hasta)
        .exclude(pedido__estado="cancelado")
        .values("producto__nombre")
        .annotate(cantidad=Sum("cantidad"), ingreso=Sum("subtotal_calculado"))
        .order_by("-cantidad")[:limit]
    )


def _cancelaciones(desde: date, hasta: date):
    return list(
        Pedido.objects
        .filter(estado="cancelado",
                fecha_hora_ingreso__date__gte=desde,
                fecha_hora_ingreso__date__lte=hasta)
        .select_related("sesion__mesa")
        .values("id", "fecha_hora_ingreso", "motivo_cancelacion",
                "sesion__mesa__numero_mesa", "sesion__alias")
    )


def get_report_data(desde: date, hasta: date) -> dict:
    """Devuelve un dict con todos los datos necesarios para el reporte.

    Los campos 'total' y 'ticket_promedio' se devuelven como Decimal para
    mantener precisión. Se convierten a float/str en el punto de serialización
    (JSON en la vista, o celdas de Excel en exportar_excel).
    """
    pedidos  = _pedidos_periodo(desde, hasta)
    agg      = pedidos.aggregate(
        t=Coalesce(Sum("detalles__subtotal_calculado"), Decimal("0.00"))
    )
    total    = agg["t"]                                    # Decimal
    tickets  = pedidos.count()
    ticket_promedio = (total / tickets).quantize(Decimal("0.01")) if tickets else Decimal("0.00")
    return {
        "desde":           desde,
        "hasta":           hasta,
        "total":           total,           # Decimal — float solo al serializar
        "tickets":         tickets,
        "ticket_promedio": ticket_promedio, # Decimal
        "ventas_por_dia":  _ventas_por_dia(pedidos),
        "top_productos":   _top_productos(desde, hasta),
        "cancelaciones":   _cancelaciones(desde, hasta),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Exportación Excel
# ──────────────────────────────────────────────────────────────────────────────
# Exportación Excel
# ──────────────────────────────────────────────────────────────────────────────

def exportar_excel(desde: date, hasta: date) -> bytes:
    """Genera un archivo .xlsx y devuelve sus bytes.

    Raises:
        ImportError: si openpyxl no está instalado.
        RuntimeError: si la generación falla por cualquier otro motivo.
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise ImportError(
            "openpyxl no está instalado. Ejecuta: pip install openpyxl==3.1.2"
        )

    try:
        data = get_report_data(desde, hasta)
    except Exception as exc:
        raise RuntimeError(f"Error al obtener datos del reporte: {exc}") from exc

    try:
        wb = openpyxl.Workbook()

        # ── Hoja 1: Resumen ──────────────────────────────────────────────────────
        ws = wb.active
        ws.title = "Resumen"

        VERDE = "2D6A4F"
        VERDE_CLARO = "D8F3DC"
        GRIS = "F8F9FA"

        header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill("solid", fgColor=VERDE)
        subheader_font = Font(name="Calibri", bold=True, size=10)
        subheader_fill = PatternFill("solid", fgColor=VERDE_CLARO)
        center = Alignment(horizontal="center", vertical="center")
        thin = Side(style="thin", color="CCCCCC")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        def _header(ws, row, col, text, span=1):
            cell = ws.cell(row=row, column=col, value=text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border
            if span > 1:
                ws.merge_cells(start_row=row, start_column=col,
                               end_row=row, end_column=col + span - 1)
            return cell

        def _cell(ws, row, col, value, fmt=None, bold=False):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = border
            if fmt:
                cell.number_format = fmt
            if bold:
                cell.font = Font(bold=True)
            return cell

        # Título
        ws.merge_cells("A1:E1")
        title_cell = ws["A1"]
        title_cell.value = f"Reporte Mochi Matcha  |  {desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}"
        title_cell.font = Font(name="Calibri", bold=True, size=14, color=VERDE)
        title_cell.alignment = center
        ws.row_dimensions[1].height = 28

        # KPIs
        _header(ws, 3, 1, "INDICADOR", 2)
        _header(ws, 3, 3, "VALOR", 2)
        kpis = [
            ("Ventas totales", f"${data['total']:,.2f}"),
            ("Pedidos procesados", data["tickets"]),
            ("Ticket promedio", f"${data['ticket_promedio']:,.2f}"),
            ("Cancelaciones", len(data["cancelaciones"])),
        ]
        for i, (k, v) in enumerate(kpis, start=4):
            fill = PatternFill("solid", fgColor=GRIS if i % 2 == 0 else "FFFFFF")
            for col in range(1, 5):
                c = ws.cell(row=i, column=col)
                c.fill = fill
                c.border = border
            ws.cell(row=i, column=1, value=k).font = Font(bold=True)
            ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
            ws.cell(row=i, column=3, value=v)
            ws.merge_cells(start_row=i, start_column=3, end_row=i, end_column=4)

        for col in range(1, 6):
            ws.column_dimensions[get_column_letter(col)].width = 22

        # ── Hoja 2: Ventas por día ───────────────────────────────────────────────
        ws2 = wb.create_sheet("Ventas por día")
        _header(ws2, 1, 1, "FECHA")
        _header(ws2, 1, 2, "PEDIDOS")
        _header(ws2, 1, 3, "TOTAL ($)")
        for i, row in enumerate(data["ventas_por_dia"], start=2):
            _cell(ws2, i, 1, _make_naive(row.get("fecha")), "DD/MM/YYYY")
            _cell(ws2, i, 2, row.get("tickets", 0))
            _cell(ws2, i, 3, float(row.get("total") or 0), "#,##0.00")
        for col in [1, 2, 3]:
            ws2.column_dimensions[get_column_letter(col)].width = 20

        # ── Hoja 3: Top productos ────────────────────────────────────────────────
        ws3 = wb.create_sheet("Productos")
        _header(ws3, 1, 1, "#")
        _header(ws3, 1, 2, "PRODUCTO")
        _header(ws3, 1, 3, "CANTIDAD VENDIDA")
        _header(ws3, 1, 4, "INGRESOS ($)")
        for i, row in enumerate(data["top_productos"], start=2):
            _cell(ws3, i, 1, i - 1)
            _cell(ws3, i, 2, row.get("producto__nombre", "—"))
            _cell(ws3, i, 3, int(row.get("cantidad") or 0))
            _cell(ws3, i, 4, float(row.get("ingreso") or 0), "#,##0.00")
        ws3.column_dimensions["A"].width = 6
        ws3.column_dimensions["B"].width = 35
        ws3.column_dimensions["C"].width = 20
        ws3.column_dimensions["D"].width = 20

        # ── Hoja 4: Cancelaciones ────────────────────────────────────────────────
        ws4 = wb.create_sheet("Cancelaciones")
        _header(ws4, 1, 1, "ID")
        _header(ws4, 1, 2, "FECHA")
        _header(ws4, 1, 3, "MESA")
        _header(ws4, 1, 4, "CLIENTE")
        _header(ws4, 1, 5, "MOTIVO")
        for i, row in enumerate(data["cancelaciones"], start=2):
            _cell(ws4, i, 1, row.get("id"))
            _cell(ws4, i, 2, _make_naive(row.get("fecha_hora_ingreso")), "DD/MM/YYYY HH:MM")
            _cell(ws4, i, 3, row.get("sesion__mesa__numero_mesa"))
            _cell(ws4, i, 4, row.get("sesion__alias") or "—")
            _cell(ws4, i, 5, row.get("motivo_cancelacion") or "—")
        for col, w in zip(range(1, 6), [8, 20, 10, 20, 50]):
            ws4.column_dimensions[get_column_letter(col)].width = w

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    except Exception as exc:
        raise RuntimeError(f"Error al generar el archivo Excel: {exc}") from exc


# ──────────────────────────────────────────────────────────────────────────────
# Exportación PDF (via WeasyPrint → HTML → PDF)
# ──────────────────────────────────────────────────────────────────────────────

def exportar_pdf(desde: date, hasta: date) -> bytes:
    """Genera un PDF a partir de un template HTML y devuelve bytes.

    Raises:
        ImportError: si weasyprint no está instalado.
        RuntimeError: si la renderización o generación PDF falla.
    """
    try:
        import weasyprint
    except ImportError:
        raise ImportError(
            "weasyprint no está instalado. Ejecuta: pip install weasyprint==62.3 "
            "(y reconstruye la imagen Docker con las dependencias del sistema)."
        )

    try:
        data = get_report_data(desde, hasta)
    except Exception as exc:
        raise RuntimeError(f"Error al obtener datos del reporte: {exc}") from exc

    try:
        html_str = render_to_string("gerente/reporte_pdf.html", {
            "desde": desde,
            "hasta": hasta,
            **data,
        })
        pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
        return pdf_bytes
    except Exception as exc:
        raise RuntimeError(f"Error al renderizar el PDF: {exc}") from exc
