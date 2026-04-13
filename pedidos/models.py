from django.db import models
from accounts.models import Empleado
from catalogs.models import MetodoPago, EstadoSolicitud, ModalidadIngreso
from mesas.models import Mesa, SesionCliente
from menu.models import Producto, OpcionModificador, Promocion


class Pedido(models.Model):
    ESTADOS = [
        ("recibido", "Recibido"),
        ("preparando", "Preparando"),
        ("listo", "Listo"),
        ("entregado", "Entregado"),
        ("cancelado", "Cancelado"),
    ]

    fecha_hora_ingreso = models.DateTimeField(auto_now_add=True)
    fecha_hora_entrega = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="recibido")
    motivo_cancelacion = models.TextField(null=True, blank=True)
    # PROTECT: un pedido es un registro histórico y no debe borrarse en cascada
    sesion = models.ForeignKey(
        SesionCliente, on_delete=models.PROTECT, related_name="pedidos"
    )
    # PROTECT: catálogo auxiliar
    modalidad = models.ForeignKey(
        ModalidadIngreso, on_delete=models.PROTECT, related_name="pedidos"
    )
    # SET_NULL: si el empleado es dado de baja, el pedido conserva su registro
    empleado_entrega = models.ForeignKey(
        Empleado,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pedidos_entregados",
    )

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-fecha_hora_ingreso"]

    def __str__(self):
        return f"Pedido #{self.pk} — {self.get_estado_display()}"


class DetallePedido(models.Model):
    cantidad = models.PositiveIntegerField()
    notas = models.CharField(max_length=255, null=True, blank=True)
    subtotal_calculado = models.DecimalField(max_digits=10, decimal_places=2)
    # CASCADE: los detalles son parte del pedido
    pedido = models.ForeignKey(
        Pedido, on_delete=models.CASCADE, related_name="detalles"
    )
    # PROTECT: no se puede borrar un producto que tiene pedidos históricos
    producto = models.ForeignKey(
        Producto, on_delete=models.PROTECT, related_name="detalles_pedido"
    )
    # SET_NULL: si la promo es eliminada, el detalle conserva el subtotal ya calculado
    promocion = models.ForeignKey(
        Promocion, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = "Detalle de pedido"
        verbose_name_plural = "Detalles de pedido"

    def __str__(self):
        return f"{self.cantidad}x {self.producto} (Pedido #{self.pedido_id})"


class DetalleModificador(models.Model):
    cantidad = models.PositiveIntegerField(default=1)
    precio_extra_aplicado = models.DecimalField(max_digits=10, decimal_places=2)
    # CASCADE: pertenece al detalle del pedido
    detalle = models.ForeignKey(
        DetallePedido, on_delete=models.CASCADE, related_name="modificadores"
    )
    # PROTECT: no se puede borrar una opción que ya fue aplicada en pedidos históricos
    opcion = models.ForeignKey(
        OpcionModificador, on_delete=models.PROTECT, related_name="usos"
    )

    class Meta:
        verbose_name = "Modificador aplicado"
        verbose_name_plural = "Modificadores aplicados"

    def __str__(self):
        return f"{self.opcion} en detalle #{self.detalle_id}"


class SolicitudPago(models.Model):
    TIPOS = [("individual", "Individual"), ("grupal", "Grupal")]

    fecha_hora = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    total_individual = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    total_mesa = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    propina_sugerida = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    # SET_NULL: si la sesión se cierra, la solicitud queda como registro
    sesion = models.ForeignKey(
        SesionCliente, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="solicitudes_pago"
    )
    # SET_NULL: igual para mesa
    mesa = models.ForeignKey(
        Mesa, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="solicitudes_pago"
    )
    # SET_NULL: el método puede cambiar de catálogo sin afectar el historial
    metodo_pago = models.ForeignKey(
        MetodoPago, null=True, blank=True, on_delete=models.SET_NULL
    )
    # PROTECT: el estado es un catálogo; no debe borrarse si tiene solicitudes
    estado_solicitud = models.ForeignKey(
        EstadoSolicitud, on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = "Solicitud de pago"
        verbose_name_plural = "Solicitudes de pago"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"Solicitud #{self.pk} — {self.get_tipo_display()}"
