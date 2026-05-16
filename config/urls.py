"""
config/urls.py — URL raíz del proyecto Mochi Matcha.

Estructura de rutas:
  /                  → redirige a /bienvenida/ (menú cliente)
  /mantenimiento/    → página de mantenimiento (controlada por MaintenanceModeMiddleware)
  /admin/            → Django Admin
  /accounts/         → login/logout genérico de staff
  /                  → rutas del módulo cliente (bienvenida, menú, carrito, etc.)
  /mesero/           → panel del mesero
  /cocina/           → KDS cocina/bar
  /gerente/          → dashboard y configuración

En DEBUG, también sirve los archivos de MEDIA_ROOT (imágenes subidas).
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView, TemplateView
from django.views.static import serve
from django.shortcuts import render


def mantenimiento_view(request):
    """
    Vista de la página de mantenimiento. Lee el mensaje personalizado desde
    la tabla Configuracion (clave 'mensaje_mantenimiento') para mostrarlo
    en la plantilla. Si la tabla aún no existe (primera migración), usa
    cadena vacía como mensaje.
    """
    from apps.gerente.models import Configuracion
    try:
        msg = Configuracion.objects.filter(clave='mensaje_mantenimiento').first()
        mensaje = msg.valor if msg else ''
    except Exception:
        mensaje = ''
    return render(request, 'mantenimiento.html', {'mensaje': mensaje})


def cerrado_view(request):
    """
    Vista de "fuera de horario" (3.1). Muestra cuándo abre el local la próxima
    vez para que el cliente sepa cuándo volver. El cálculo se hace aquí en vez
    del middleware para que la página principal no tenga el costo en cada hit.
    """
    from datetime import datetime, timedelta
    from django.utils import timezone
    from apps.gerente.models import HorarioAtencion
    proximo = None
    try:
        ahora = timezone.localtime(timezone.now())
        hoy   = ahora.weekday()
        hora  = ahora.time()
        horarios = list(HorarioAtencion.objects.filter(activo=True).order_by('dia_semana', 'abre'))
        if horarios:
            # Buscar el próximo rango: hoy con apertura aún por venir, o en los
            # próximos 6 días.
            for offset in range(0, 8):
                dia = (hoy + offset) % 7
                for h in horarios:
                    if h.dia_semana != dia:
                        continue
                    if offset == 0 and h.abre <= hora:
                        continue
                    candidato = ahora.replace(hour=h.abre.hour, minute=h.abre.minute,
                                              second=0, microsecond=0) + timedelta(days=offset)
                    proximo = (candidato, h)
                    break
                if proximo:
                    break
    except Exception:
        proximo = None
    return render(request, 'cerrado.html', {'proximo': proximo})


urlpatterns = [
    path("", RedirectView.as_view(url="/bienvenida/"), name="root"),
    path("mantenimiento/", mantenimiento_view, name="mantenimiento"),
    path("cerrado/", cerrado_view, name="cerrado"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.cliente.urls")),
    path("mesero/", include("apps.mesero.urls")),
    path("cocina/", include("apps.cocina.urls")),
    path("gerente/", include("apps.gerente.urls")),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]