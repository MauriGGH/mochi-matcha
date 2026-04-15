from django.contrib import admin
from .models import ModalidadIngreso, MetodoPago, EstadoSolicitud

admin.site.register(ModalidadIngreso)
admin.site.register(MetodoPago)
admin.site.register(EstadoSolicitud)