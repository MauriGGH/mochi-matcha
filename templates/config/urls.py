from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/bienvenida/"), name="root"),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.cliente.urls")),
    path("mesero/", include("apps.mesero.urls")),
    path("cocina/", include("apps.cocina.urls")),
    path("gerente/", include("apps.gerente.urls")),
]
