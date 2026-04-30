from django.db import models
from apps.accounts.models import Empleado
from apps.catalogs.models import ModalidadIngreso
import qrcode
from io import BytesIO
import base64
from django.urls import reverse
from django.conf import settings


class UbicacionMesa(models.Model):
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
    ESTADOS = [("libre", "Libre"), ("ocupada", "Ocupada")]

    numero_mesa = models.IntegerField(unique=True)
    capacidad = models.IntegerField()
    ubicacion = models.ForeignKey(
        UbicacionMesa, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="mesas"
    )
    codigo_qr = models.CharField(max_length=255, unique=True)
    pin_actual = models.CharField(max_length=60, null=True, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default="libre")
    id_mesero_asignado = models.ForeignKey(
        Empleado,
        null=True, blank=True,
        on_delete=models.SET_NULL,
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

    def generate_qr_base64(self):
        """Genera QR en base64 para mostrar en el admin"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        base_url = getattr(settings, "SITE_BASE_URL", "http://localhost:8000")
        full_url = base_url + self.get_qr_url()
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

    def __str__(self):
        return f"{self.alias} @ {self.mesa}"


class AlertaMesero(models.Model):
    TIPOS = [
        ("ayuda", "Ayuda"),
        ("cuenta", "Solicitud de cuenta"),
        ("personalizado", "Personalizado"),
    ]

    mesa = models.ForeignKey(Mesa, on_delete=models.CASCADE, related_name="alertas")
    sesion = models.ForeignKey(
        SesionCliente, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="alertas"
    )
    tipo = models.CharField(max_length=15, choices=TIPOS, default="ayuda")
    mensaje = models.TextField(blank=True, default="")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    atendida = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Alerta de mesero"
        verbose_name_plural = "Alertas de mesero"
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.get_tipo_display()} — Mesa {self.mesa.numero_mesa}"