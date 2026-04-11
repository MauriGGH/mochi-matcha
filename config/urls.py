"""
mochi_matcha — URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Raíz → bienvenida
    path("", RedirectView.as_view(url="/bienvenida/"), name="root"),

    # Django admin — solo superusuarios en mantenimiento
    path("admin/", admin.site.urls),

    # ── Cuentas (logout compartido del staff) ──────────────────────────
    path("accounts/", include("accounts.urls")),

    # ── Módulo cliente (sin autenticación Django; usa cookie propia) ──
    # Acceso: /  →  /bienvenida/?mesa=5
    #          /menu/, /carrito/, /pedidos/, etc.
    path("", include("cliente.urls")),

    # ── Módulo mesero ──────────────────────────────────────────────────
    # Acceso: /mesero/login/  →  /mesero/mesas/
    path("mesero/", include("mesero.urls")),

    # ── Módulo cocina (KDS) ────────────────────────────────────────────
    # Acceso: /cocina/login/  →  /cocina/kds/?area=cocina
    path("cocina/", include("cocina.urls")),

    # ── Módulo gerente / admin ────────────────────────────────────────
    # Acceso: /gerente/login/  →  /gerente/dashboard/
    path("gerente/", include("gerente.urls")),
]