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
