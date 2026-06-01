"""
apps/auditoria/models.py — Registro de auditoría de acciones del sistema.

Cada entrada registra una acción relevante (apertura de mesa, cancelación de pedido,
cobro, etc.) vinculando el empleado responsable con la entidad afectada.
Los campos FK usan SET_NULL para que el registro de auditoría NUNCA se pierda aunque
se eliminen empleados, mesas o pedidos relacionados — es un log inmutable de negocio.
"""
from django.db import models
from apps.accounts.models import Empleado
from apps.mesas.models import Mesa
from apps.pedidos.models import Pedido, SolicitudPago


class Auditoria(models.Model):
    """
    Entrada de auditoría de una acción del sistema.

    `accion`: descripción corta de la acción (ej. 'COBRO_MESA', 'CANCELAR_PEDIDO').
    `detalle`: JSON o texto libre con información adicional (montos, motivos, etc.).
    `empleado`: PROTECT — el registro de auditoría es inmutable; no puede perderse
                si el empleado es dado de baja. El FK se conserva apuntando al registro
                existente; la baja se gestiona poniendo Empleado.is_active = False.
    `mesa`, `pedido`, `solicitud_pago`: SET_NULL — referencias opcionales a la entidad
                afectada. La auditoría se conserva aunque la entidad sea eliminada.
    """
    fecha_hora = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=100)
    detalle = models.TextField(null=True, blank=True)
    # PROTECT: la auditoría no debe borrarse si se da de baja un empleado
    empleado = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, related_name="auditorias"
    )
    # SET_NULL: si la mesa es eliminada, el registro de auditoría se conserva
    mesa = models.ForeignKey(
        Mesa, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )
    # SET_NULL: si el pedido es eliminado (no debería), la auditoría se conserva
    pedido = models.ForeignKey(
        Pedido, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )
    # SET_NULL: referencia a la solicitud de pago involucrada (cancelaciones, cobros)
    solicitud_pago = models.ForeignKey(
        SolicitudPago, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="auditorias"
    )

    class Meta:
        verbose_name = "Auditoría"
        verbose_name_plural = "Auditorías"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"[{self.fecha_hora:%Y-%m-%d %H:%M}] {self.accion} — {self.empleado}"
