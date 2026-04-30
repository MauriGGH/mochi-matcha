from django.urls import path
from . import views

app_name = 'cliente'

urlpatterns = [
    # Bienvenida / sesión
    path('bienvenida/', views.bienvenida, name='bienvenida'),
    path('bienvenida/crear/<int:mesa_id>/', views.crear_sesion, name='crear_sesion'),
    path('bienvenida/recuperar/<int:mesa_id>/', views.recuperar_sesion, name='recuperar_sesion'),
    path('bienvenida/pin/', views.mostrar_pin, name='mostrar_pin'),
    path('bienvenida/estado/<int:mesa_id>/', views.estado_mesa, name='estado_mesa'),

    # Menú
    path('menu/', views.menu, name='menu'),

    # Carrito
    path('carrito/', views.carrito, name='carrito'),
    path('carrito/agregar/', views.agregar_carrito, name='agregar_carrito'),
    path('carrito/actualizar/', views.actualizar_carrito, name='actualizar_carrito'),
    path('carrito/eliminar/', views.eliminar_carrito, name='eliminar_carrito'),
    path('carrito/limpiar/', views.limpiar_carrito, name='limpiar_carrito'),
    path('carrito/confirmar/', views.confirmar_pedido, name='confirmar_pedido'),
    path('carrito/calcular/', views.calcular_carrito, name='calcular_carrito'),

    # Pedidos
    path('pedidos/', views.pedidos, name='pedidos'),
    path('pedidos/estado/', views.estado_pedidos, name='estado_pedidos'),
    path('pedidos/ayuda/', views.solicitar_ayuda, name='solicitar_ayuda'),
    path('pedidos/cuenta/', views.solicitar_cuenta, name='solicitar_cuenta'),
]
