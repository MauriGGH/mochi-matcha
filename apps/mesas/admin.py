"""
apps/mesas/admin.py — Registro de modelos de mesas en el panel de administración Django.

MesaAdmin:     muestra y genera el QR de cada mesa directamente en el listado y detalle.
SesionClienteAdmin: permite consultar las sesiones activas/cerradas por mesa.
"""
from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Mesa, SesionCliente


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    """
    Administración de mesas. Los campos `codigo_qr`, `pin_actual` y `qr_preview`
    son de solo lectura para evitar edición manual que desincronice el QR físico.
    """
    list_display = ['numero_mesa', 'capacidad', 'ubicacion', 'estado', 'id_mesero_asignado', 'ver_qr']
    list_filter = ['estado', 'ubicacion']
    search_fields = ['numero_mesa']
    readonly_fields = ['qr_preview', 'pin_actual', 'codigo_qr']
    fieldsets = (
        ('Información básica', {
            'fields': ('numero_mesa', 'capacidad', 'ubicacion', 'estado')
        }),
        ('Asignación', {
            'fields': ('id_mesero_asignado', 'pin_actual')
        }),
        ('Código QR', {
            'fields': ('codigo_qr', 'qr_preview'),
            'description': 'El QR se genera automáticamente al guardar.'
        }),
    )

    def ver_qr(self, obj):
        """Renderiza una imagen del QR en miniatura para el listado del admin."""
        if obj.pk:
            return mark_safe(f'<img src="data:image/png;base64,{obj.generate_qr_base64()}" width="80"/>')
        return "-"
    ver_qr.short_description = "QR"

    def qr_preview(self, obj):
        """Renderiza el QR en tamaño normal en la vista de detalle de la mesa."""
        return self.ver_qr(obj)
    qr_preview.short_description = "Vista previa QR"


@admin.register(SesionCliente)
class SesionClienteAdmin(admin.ModelAdmin):
    """
    Administración de sesiones de cliente. `token_cookie` y `fecha_inicio` son
    de solo lectura porque son generados automáticamente al crear la sesión.
    """
    list_display = ['alias', 'mesa', 'estado', 'fecha_inicio', 'modalidad_ingreso']
    list_filter = ['estado', 'modalidad_ingreso']
    search_fields = ['alias', 'mesa__numero_mesa']
    readonly_fields = ['token_cookie', 'fecha_inicio']
    