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
