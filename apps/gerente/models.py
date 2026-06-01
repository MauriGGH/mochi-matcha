"""
Modelos del panel de gerente de Mochi Matcha.
Contiene la configuración global del sistema y los horarios de atención.
"""
from django.db import models


class Configuracion(models.Model):
    """Almacena pares clave-valor de configuración global del sistema.

    Ejemplos de claves usadas:
        semaforo_yellow / semaforo_red   — tiempos (minutos) para alertas visuales.
        modo_mantenimiento               — "true"/"false" para bloquear el POS.
        restaurante_nombre / _direccion  — datos que aparecen en el ticket impreso.
        paypal_client_id / _secret       — credenciales PayPal (sandbox o live).
        horarios_activos                 — "true"/"false". Si false, la app está
                                           abierta 24/7 (los HorarioAtencion se
                                           ignoran). Útil para temporada alta.
    """
    clave = models.CharField(max_length=100, unique=True)
    valor = models.TextField(max_length=1000)

    class Meta:
        verbose_name = "Configuración"
        verbose_name_plural = "Configuraciones"

    def __str__(self):
        return f"{self.clave} = {self.valor}"


class HorarioAtencion(models.Model):
    """
    Horario de atención del local por día de la semana.

    Si la clave de configuración `horarios_activos` está en "true" y hay al
    menos un HorarioAtencion habilitado, el middleware `HorarioMiddleware`
    bloquea el acceso de clientes fuera del rango configurado (el staff sigue
    pasando). Si no hay horarios para el día actual, el local se considera
    cerrado ese día completo.

    Soporta horarios que cruzan medianoche (ej. abre 18:00 cierra 02:00) si
    cierra < abre — el middleware lo trata como abierto hasta cierra del día
    siguiente.
    """
    DIAS = [
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    dia_semana = models.IntegerField(choices=DIAS)
    abre = models.TimeField(help_text="Hora de apertura (formato 24h, ej. 08:00)")
    cierra = models.TimeField(help_text="Hora de cierre (formato 24h, ej. 22:00)")
    activo = models.BooleanField(
        default=True,
        help_text="Si está desactivado, este día se considera cerrado.",
    )

    class Meta:
        verbose_name = "Horario de atención"
        verbose_name_plural = "Horarios de atención"
        ordering = ["dia_semana", "abre"]
        # Un día puede tener varios horarios (ej. partido: 08-14 y 17-22).
        # No imponemos unique_together: el gerente decide cuántos rangos por día.

    def __str__(self):
        return f"{self.get_dia_semana_display()} {self.abre:%H:%M}-{self.cierra:%H:%M}"

    def cubre(self, hora_actual):
        """
        ¿La `hora_actual` (datetime.time) cae dentro de este rango?
        Maneja horarios que cruzan medianoche.
        """
        if self.abre <= self.cierra:
            return self.abre <= hora_actual < self.cierra
        # Cruza medianoche (ej. abre 22:00, cierra 02:00):
        # hora_actual está dentro si >= abre O < cierra.
        return hora_actual >= self.abre or hora_actual < self.cierra
