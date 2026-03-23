from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(Empleado)
admin.site.register(ModalidadIngreso)
admin.site.register(Categoria)
admin.site.register(TipoPromocion)
admin.site.register(Promocion)
admin.site.register(Mesa)
admin.site.register(Producto)
admin.site.register(GrupoModificador)
admin.site.register(OpcionModificador)
admin.site.register(MetodoPago)
admin.site.register(EstadoSolicitud)
admin.site.register(SesionCliente)
admin.site.register(PromocionProducto)
admin.site.register(Pedido)
admin.site.register(DetallePedido)
admin.site.register(DetalleModificador)
admin.site.register(SolicitudPago)
admin.site.register(Auditoria)
