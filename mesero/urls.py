from django.urls import path
from . import views

app_name = 'mesero'

urlpatterns = [
    path('login/', views.login_mesero, name='login_mesero'),
    path('logout/', views.logout_mesero, name='logout_mesero'),
    path('mapa/', views.mapa_mesas, name='mapa_mesas'),
    path('mapa/estado/', views.mesas_estado, name='mesas_estado'),
    path('mapa/<int:mesa_id>/', views.detalle_mesa, name='detalle_mesa'),
    path('pedidos-listos/', views.pedidos_listos, name='pedidos_listos'),
    path('pedidos/entregar/', views.entregar_pedido, name='entregar_pedido'),
    path('sesion/cerrar/', views.cerrar_sesion, name='cerrar_sesion'),
    path('mesa/cerrar/', views.cerrar_mesa, name='cerrar_mesa'),
    path('asistido/', views.pedido_asistido, name='pedido_asistido'),
    path('asistido/confirmar/', views.confirmar_pedido_asistido, name='confirmar_pedido_asistido'),
    path('alertas/', views.alertas, name='alertas'),
    path('cuentas/', views.cuentas, name='cuentas'),
    path('pago/', views.pago, name='pago'),
    path('pago/procesar/', views.procesar_pago, name='procesar_pago'),
    path('mesas/', views.mapa_mesas, name='mesas'),
]
