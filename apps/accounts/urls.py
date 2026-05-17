"""
apps/accounts/urls.py — Rutas de autenticación global.

Prefijo: /accounts/  (ver config/urls.py)
Namespace: accounts

/accounts/login/    → login genérico que redirige según el rol del empleado.
/accounts/logout/   → cierre de sesión universal (para cualquier rol de staff).
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('logout/', views.logout_view, name='logout'),
    path('login/', views.login_view, name='login'),
]
