"""
apps/mesas/models.py — Modelos de mesas, sesiones de cliente y alertas de mesero.

Flujo principal:
  Mesa (QR) → SesionCliente (token cookie) → Pedido(s) → SolicitudPago
  AlertaMesero se genera desde el menú del cliente para solicitar ayuda o la cuenta.
"""
from django.db import models
from apps.accounts.models import Empleado
from apps.catalogs.models import ModalidadIngreso
import qrcode
from io import BytesIO
import base64
from django.urls import reverse
from django.conf import settings


class UbicacionMesa(models.Model):
    """
    Agrupación física de mesas (ej. 'Terraza', 'Interior', 'Barra').
    Permite filtrar y organizar el mapa de mesas en el panel del mesero.
    El nombre se normaliza a MAYÚSCULAS en save().
    """
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        verbose_name = "Ubicación de mesa"
        verbose_name_plural = "Ubicaciones de mesa"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.nombre:
            self.nombre = self.nombre.upper()
        super().save(*args, **kwargs)


class Mesa(models.Model):
    """
    Mesa física del restaurante. Es el punto de entrada para la experiencia del cliente.

    `numero_mesa`: identificador humano visible en el KDS y en tickets.
    `codigo_qr`: token único generado automáticamente (UUID parcial) que se incrusta
                 en el QR físico. No es la URL completa; esta se construye en get_qr_url().
    `pin_actual`: PIN opcional usado en algunos flujos de verificación de mesa; puede
                  quedar en blanco si no se usa el flujo de PIN.
    `estado`: 'libre' / 'ocupada' — refleja si hay una sesión activa.
    `id_mesero_asignado`: mesero responsable de la mesa; SET_NULL para que la mesa
                          no se pierda si el empleado es dado de baja.
    `ubicacion`: SET_NULL — si se borra una ubicación, las mesas quedan sin asignar
                 pero no se eliminan.
    """
    ESTADOS = [("libre", "Libre"), ("ocupada", "Ocupada")]

    numero_mesa = models.IntegerField(unique=True)
    capacidad = models.IntegerField()
    ubicacion = models.ForeignKey(
        UbicacionMesa, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mesas"  # SET_NULL: mesa sobrevive al borrar ubicación
    )
    codigo_qr = models.CharField(max_length=255, unique=True)
    pin_actual = models.CharField(max_length=60, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="libre")
    # Nota visible en el mapa del mesero cuando, tras un cobro, la mesa NO se
    # libera automáticamente. Se rellena con un motivo (p.ej. "cuenta saldada,
    # cerrar manualmente" o "queda $X sin cobrar"). El mesero cierra la mesa
    # con el botón "Cerrar mesa", que limpia este campo.
    nota_cierre = models.CharField(max_length=255, blank=True, default="")
    id_mesero_asignado = models.ForeignKey(
        Empleado,
        null=True, blank=True,
        on_delete=models.SET_NULL,  # SET_NULL: la mesa no se borra si el mesero es dado de baja
        related_name="mesas_asignadas",
        limit_choices_to={"rol": "mesero"},
    )

    class Meta:
        verbose_name = "Mesa"
        verbose_name_plural = "Mesas"
        ordering = ["numero_mesa"]

    def __str__(self):
        return f"Mesa {self.numero_mesa}"

    # ─── Métodos para QR ──────────────────────────────────────────────
    def get_qr_url(self):
        """Devuelve la URL relativa que debe contener el QR"""
        return reverse('cliente:bienvenida') + f'?mesa={self.pk}'

    def generate_qr_base64(self, base_url=None):
        """
        Genera el QR en base64.

        base_url: dominio absoluto al que debe apuntar el QR (sin barra final).
        Si se pasa (p. ej. desde la vista con request.build_absolute_uri), el QR
        usa el dominio real con el que se accede al sistema — así funciona en
        producción sin reconfigurar nada al cambiar de dominio.
        Si no se pasa, cae a settings.SITE_BASE_URL como respaldo.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        if not base_url:
            base_url = getattr(settings, "SITE_BASE_URL", "http://localhost:8000")
        full_url = base_url.rstrip("/") + self.get_qr_url()
        qr.add_data(full_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def save(self, *args, **kwargs):
        # Generar código QR único si no existe
        if not self.codigo_qr:
            import uuid
            self.codigo_qr = f"mesa-{self.numero_mesa}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)


class SesionCliente(models.Model):
    """
    Sesión de un grupo de clientes en una mesa desde que escanean el QR hasta el pago.

    `alias`: nombre que el cliente ingresa al inicio (ej. 'Mesa 3 - Juan').
             Normalizado a MAYÚSCULAS. Aparece en el KDS y en el panel del mesero.
    `token_cookie`: UUID almacenado en la cookie del navegador del cliente. Permite
                    identificar a cada sesión de forma anónima y persistente entre
                    páginas sin necesitar login.
    `estado`: 'activa' mientras el cliente puede pedir; 'pagada' tras confirmar pago;
              'cerrada' al terminar la visita.
    `mesa`: PROTECT — no se puede borrar una mesa con sesiones activas.
    `modalidad_ingreso`: PROTECT — catálogo auxiliar inmutable.
    """
    ESTADOS = [
        ("activa", "Activa"),
        ("pagada", "Pagada"),
        ("cerrada", "Cerrada"),
    ]

    alias = models.CharField(max_length=50)
    token_cookie = models.CharField(max_length=255, unique=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="activa")
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="sesiones")
    modalidad_ingreso = models.ForeignKey(
        ModalidadIngreso, on_delete=models.PROTECT, related_name="sesiones"
    )

    class Meta:
        verbose_name = "Sesión de cliente"
        verbose_name_plural = "Sesiones de clientes"

    def save(self, *args, **kwargs):
        if self.alias:
            self.alias = self.alias.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.alias} @ {self.mesa}"


class AlertaMesero(models.Model):
    """
    Notificación generada por el cliente desde el menú digital para llamar al mesero.

    `tipo`: distingue entre solicitud de ayuda genérica, solicitud de cuenta y
            mensajes personalizados libres.
    `atendida`: el mesero la marca True desde su panel para que desaparezca de la cola.
    `sesion`: SET_NULL — la alerta se conserva si la sesión es cerrada/borrada.
    `mesa`: CASCADE — si se elimina la mesa, sus alertas ya no tienen sentido.
    El mensaje se normaliza a MAYÚSCULAS en save().
    """
    TIPOS = [
        ("ayuda", "Ayuda"),
        ("cuenta", "Solicitud de cuenta"),
        ("personalizado", "Personalizado"),
    ]

    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE, related_name="alertas")
    sesion = models.ForeignKey(
        SesionCliente, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="alertas"  # SET_NULL: la alerta sobrevive al cerrar sesión
    )
    tipo = models.CharField(max_length=15, choices=TIPOS, default="ayuda")
    mensaje = models.TextField(blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    atendida = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Alerta de mesero"
        verbose_name_plural = "Alertas de mesero"
        ordering = ["-fecha_creacion"]

    def save(self, *args, **kwargs):
        if self.mensaje:
            self.mensaje = self.mensaje.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_tipo_display()} — Mesa {self.mesa.numero_mesa}"