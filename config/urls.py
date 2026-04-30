from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView
from django.shortcuts import render


def mantenimiento_view(request):
    from apps.gerente.models import Configuracion
    try:
        msg = Configuracion.objects.filter(clave='mensaje_mantenimiento').first()
        mensaje = msg.valor if msg else ''
    except Exception:
        mensaje = ''
    return render(request, 'mantenimiento.html', {'mensaje': mensaje})


urlpatterns = [
    path("", RedirectView.as_view(url="/bienvenida/"), name="root"),
    path("mantenimiento/", mantenimiento_view, name="mantenimiento"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.cliente.urls")),
    path("mesero/", include("apps.mesero.urls")),
    path("cocina/", include("apps.cocina.urls")),
    path("gerente/", include("apps.gerente.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)