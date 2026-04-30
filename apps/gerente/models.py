from django.db import models


class Configuracion(models.Model):
    """Almacena pares clave-valor de configuración global del sistema."""
    clave = models.CharField(max_length=100, unique=True)
    valor = models.TextField()

    class Meta:
        verbose_name = "Configuración"
        verbose_name_plural = "Configuraciones"

    def __str__(self):
        return f"{self.clave} = {self.valor}"
