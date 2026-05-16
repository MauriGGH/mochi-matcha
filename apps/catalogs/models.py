"""
apps/catalogs/models.py — Catálogos auxiliares del sistema.

Estos modelos son tablas de referencia (catálogos) que no deben borrarse
mientras existan registros relacionados. Se usan como FK con on_delete=PROTECT
en los modelos principales (SesionCliente, Pedido, SolicitudPago).

Catálogos incluidos:
  ModalidadIngreso: cómo llegó el cliente (QR, asistido, etc.).
  MetodoPago:       efectivo, tarjeta, mixto, PayPal, etc.
  EstadoSolicitud:  estados de una solicitud de pago (pendiente, aprobada, etc.).
"""
from django.db import models


class ModalidadIngreso(models.Model):
    """
    Cómo ingresó el cliente: QR, asistido por mesero, etc.
    Catálogo — no debe borrarse si tiene sesiones asociadas.
    """
    descripcion = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Modalidad de ingreso"
        verbose_name_plural = "Modalidades de ingreso"

    def __str__(self):
        return self.descripcion


class MetodoPago(models.Model):
    """
    Efectivo, tarjeta, mixto, etc.
    Catálogo auxiliar.
    """
    descripcion = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Método de pago"
        verbose_name_plural = "Métodos de pago"

    def __str__(self):
        return self.descripcion


class EstadoSolicitud(models.Model):
    """
    Estados para las solicitudes de pago: pendiente, procesada, cancelada, etc.
    Catálogo auxiliar.
    """
    descripcion = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Estado de solicitud"
        verbose_name_plural = "Estados de solicitud"

    def __str__(self):
        return self.descripcion
