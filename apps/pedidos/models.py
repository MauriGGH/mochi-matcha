"""
apps/pedidos/models.py — Modelos del ciclo de vida de un pedido.

Flujo de estados de Pedido:
  recibido → preparando → listo → entregado
                                  └→ cancelado (desde cualquier estado)

El estado "listo" solo se alcanza cuando TODOS los DetallePedido.listo == True,
lo que garantiza que cocina y bar hayan terminado sus ítems respectivos.
"""
from django.db import models
from apps.accounts.models import Empleado
from apps.catalogs.models import MetodoPago, EstadoSolicitud, ModalidadIngreso
from apps.mesas.models import Mesa, SesionCliente
from apps.menu.models import Producto, OpcionModificador, Promocion


class Pedido(models.Model):
    """
    Pedido creado por un cliente desde la sesión de mesa.

    `token_idempotencia`: token único por intento de confirmación. Evita que doble
                          click o requests concurrentes generen pedidos duplicados;
                          la unicidad la garantiza la constraint UNIQUE de la BD.
    `sesion`: PROTECT — un pedido es un registro histórico; no puede perderse si
              se cierra la sesión.
    `modalidad`: PROTECT — catálogo auxiliar; no debe borrarse con pedidos activos.
    `empleado_entrega`: SET_NULL — el historial se conserva aunque el mesero sea dado
                        de baja.
    """
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
    motivo_cancelacion = models.CharField(max_length=500, blank=True, default="")
    # Idempotencia: token único por intento de confirmación de carrito. Evita
    # que un doble-click o dos requests concurrentes creen pedidos duplicados
    # (la unicidad la garantiza la BD, no solo el frontend).
    token_idempotencia = models.CharField(
        max_length=64, null=True, blank=True, unique=True,
    )
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

    def save(self, *args, **kwargs):
        if self.motivo_cancelacion:
            self.motivo_cancelacion = self.motivo_cancelacion.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pedido #{self.pk} — {self.get_estado_display()}"


class DetallePedido(models.Model):
    """
    Una línea del pedido: un producto con su cantidad, modificadores y subtotal.

    `subtotal_calculado`: precio final ya con promociones y modificadores aplicados,
                          calculado en el momento del pedido y congelado aquí para
                          que cambios posteriores en precios no alteren el histórico.
    `notas`: instrucciones especiales del cliente para ese ítem (alergia, sin azúcar…).
    `listo`: flag por ítem para el KDS multiárea. Ver comentario inline abajo.
    `fecha_listo`: momento en que el área marcó el ítem como listo (útil para reportes).
    `promocion`: SET_NULL — si la promo es eliminada, el subtotal ya calculado
                 permanece intacto en el detalle.
    """
    cantidad = models.PositiveIntegerField()
    notas = models.CharField(max_length=255, null=True, blank=True)
    subtotal_calculado = models.DecimalField(max_digits=10, decimal_places=2)
    # Estado de preparación POR ÍTEM. Permite que un pedido con productos de
    # cocina y bar avance por áreas independientes: el pedido global solo pasa
    # a "listo" cuando TODOS sus detalles están listos.
    listo = models.BooleanField(
        default=False,
        help_text="True cuando el área correspondiente terminó este ítem.",
    )
    fecha_listo = models.DateTimeField(null=True, blank=True)
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

    def save(self, *args, **kwargs):
        if self.notas:
            self.notas = self.notas.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cantidad}x {self.producto} (Pedido #{self.pedido_id})"


class DetalleModificador(models.Model):
    cantidad = models.PositiveIntegerField(default=1)
    precio_extra_aplicado = models.DecimalField(max_digits=10, decimal_places=2)
    # Snapshot del nombre en el momento del pedido (histórico inmutable)
    nombre_opcion_historico = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Nombre de la opción en el momento en que se creó el pedido."
    )
    # CASCADE: pertenece al detalle del pedido
    detalle = models.ForeignKey(
        DetallePedido, on_delete=models.CASCADE, related_name="modificadores"
    )
    # PROTECT: no se puede borrar una opción que ya fue aplicada en pedidos históricos
    opcion = models.ForeignKey(
        OpcionModificador, on_delete=models.PROTECT, related_name="usos"
    )

    @property
    def nombre_display(self):
        """Devuelve el nombre histórico si existe, o el nombre actual de la opción."""
        return self.nombre_opcion_historico or self.opcion.nombre_opcion

    class Meta:
        verbose_name = "Modificador aplicado"
        verbose_name_plural = "Modificadores aplicados"

    def __str__(self):
        return f"{self.nombre_display} en detalle #{self.detalle_id}"


class SolicitudPago(models.Model):
    """
    Solicitud de pago generada cuando el cliente pide la cuenta desde el menú.

    `tipo`: 'individual' = el cliente paga solo su consumo; 'grupal' = la mesa entera.
    `total_individual`: monto calculado para el cliente solicitante.
    `total_mesa`: suma de todos los pedidos de la sesión (pago grupal).
    `propina_sugerida`: monto precomputado sugerido al cliente (normalmente 10-15%).
    `sesiones_cubiertas`: M2M que registra qué sesiones cubre este pago, permitiendo
                          reconstruir exactamente qué consumos forman el ticket final.
    `monto_efectivo` / `monto_tarjeta`: desglose para pago mixto (efectivo + tarjeta).
    `monto_recibido` / `cambio`: para el flujo de efectivo: cuánto entregó el cliente
                                  y cuánto se le devolvió.
    `detalle_pago`: texto libre para imprimir en el ticket (desglose por ítem).
    `referencia_externa`: ID de orden PayPal u otra pasarela de pago.
    `estado_solicitud`: PROTECT — catálogo de estados; no debe borrarse con solicitudes.
    """
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
    # Sesiones efectivamente cubiertas por esta solicitud. Para un pago grupal
    # registra QUÉ sesiones se saldaron, de modo que el ticket reconstruya solo
    # los pedidos de esta visita y no el histórico de la mesa.
    sesiones_cubiertas = models.ManyToManyField(
        SesionCliente, blank=True, related_name="solicitudes_que_la_cubren",
    )
    # SET_NULL: el método puede cambiar de catálogo sin afectar el historial
    metodo_pago = models.ForeignKey(
        MetodoPago, null=True, blank=True, on_delete=models.SET_NULL
    )
    # PROTECT: el estado es un catálogo; no debe borrarse si tiene solicitudes
    estado_solicitud = models.ForeignKey(
        EstadoSolicitud, on_delete=models.PROTECT
    )

    # Campos de detalle de pago (nuevos)
    monto_efectivo = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Monto pagado en efectivo (pago mixto)."
    )
    monto_tarjeta = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Monto pagado con tarjeta (pago mixto)."
    )
    monto_recibido = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Efectivo físico recibido del cliente."
    )
    cambio = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cambio entregado al cliente."
    )
    detalle_pago = models.TextField(
        blank=True, default='',
        help_text="Desglose del pago para imprimir en ticket."
    )
    referencia_externa = models.CharField(
        max_length=200, blank=True, default='',
        help_text="ID de orden PayPal u otra referencia externa."
    )

    class Meta:
        verbose_name = "Solicitud de pago"
        verbose_name_plural = "Solicitudes de pago"
        ordering = ["-fecha_hora"]

    def __str__(self):
        return f"Solicitud #{self.pk} — {self.get_tipo_display()}"
