"""
cocina/urls.py — Rutas del módulo KDS (Kitchen Display System).

Prefijo montado en: /cocina/  (ver config/urls.py)
Namespace:          cocina

Rutas expuestas
---------------
/cocina/login/          → login exclusivo para personal de cocina/bar.
/cocina/logout/         → cierre de sesión y retorno al login.
/cocina/kds/            → pantalla principal del KDS (vista HTML).
/cocina/pedidos-json/   → endpoint de polling; devuelve JSON con pendientes y listos.
/cocina/marcar-listo/   → endpoint POST para avanzar el estado de un pedido por área.
"""
from django.urls import path
from . import views

app_name = 'cocina'

urlpatterns = [
    path('login/', views.login_cocina, name='login_cocina'),
    path('logout/', views.logout_cocina, name='logout_cocina'),
    path('kds/', views.kds, name='kds'),
    path('pedidos-json/', views.pedidos_json, name='pedidos_json'),
    path('marcar-listo/', views.marcar_listo, name='marcar_listo'),
]
