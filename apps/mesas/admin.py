from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Mesa, SesionCliente


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
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
        if obj.pk:
            return mark_safe(f'<img src="data:image/png;base64,{obj.generate_qr_base64()}" width="80"/>')
        return "-"
    ver_qr.short_description = "QR"

    def qr_preview(self, obj):
        return self.ver_qr(obj)
    qr_preview.short_description = "Vista previa QR"


@admin.register(SesionCliente)
class SesionClienteAdmin(admin.ModelAdmin):
    list_display = ['alias', 'mesa', 'estado', 'fecha_inicio', 'modalidad_ingreso']
    list_filter = ['estado', 'modalidad_ingreso']
    search_fields = ['alias', 'mesa__numero_mesa']
    readonly_fields = ['token_cookie', 'fecha_inicio']
    