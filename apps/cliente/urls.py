"""
cliente/urls.py — Tabla de rutas del módulo de cliente final.
Todas las URLs bajo el namespace 'cliente'; la mayoría requiere cookie mm_session.
"""
from django.urls import path
from . import views

app_name = 'cliente'

urlpatterns = [
    # ── Bienvenida / sesión ─────────────────────────────────────────────────────
    # Flujo QR: el cliente escanea el QR de la mesa, llega a /bienvenida/ y crea
    # o recupera su sesión. Estas rutas NO requieren cookie activa.
    path('bienvenida/', views.bienvenida, name='bienvenida'),
    path('bienvenida/crear/<int:mesa_id>/', views.crear_sesion, name='crear_sesion'),
    path('bienvenida/recuperar/<int:mesa_id>/', views.recuperar_sesion, name='recuperar_sesion'),
    path('bienvenida/pin/', views.mostrar_pin, name='mostrar_pin'),
    path('bienvenida/estado/<int:mesa_id>/', views.estado_mesa, name='estado_mesa'),

    # ── Menú ────────────────────────────────────────────────────────────────────
    path('menu/', views.menu, name='menu'),

    # ── Carrito ─────────────────────────────────────────────────────────────────
    # Operaciones CRUD sobre el carrito almacenado en sesión Django.
    # /calcular/ es informativo (descuentos estimados); /confirmar/ crea el Pedido real.
    path('carrito/', views.carrito, name='carrito'),
    path('carrito/agregar/', views.agregar_carrito, name='agregar_carrito'),
    path('carrito/actualizar/', views.actualizar_carrito, name='actualizar_carrito'),
    path('carrito/eliminar/', views.eliminar_carrito, name='eliminar_carrito'),
    path('carrito/limpiar/', views.limpiar_carrito, name='limpiar_carrito'),
    path('carrito/confirmar/', views.confirmar_pedido, name='confirmar_pedido'),
    path('carrito/calcular/', views.calcular_carrito, name='calcular_carrito'),

    # ── Pedidos ─────────────────────────────────────────────────────────────────
    # /estado/ es el endpoint de polling del cliente; /ayuda/ y /cuenta/ generan alertas al mesero.
    path('pedidos/', views.pedidos, name='pedidos'),
    path('pedidos/estado/', views.estado_pedidos, name='estado_pedidos'),
    path('pedidos/ayuda/', views.solicitar_ayuda, name='solicitar_ayuda'),
    path('pedidos/cuenta/', views.solicitar_cuenta, name='solicitar_cuenta'),

    # ── Estado de la sesión (detección de pago) + cierre voluntario ─────────────
    # /sesion/estado/ es el polling que detecta cuando el mesero cobra la cuenta.
    path('sesion/estado/', views.estado_sesion, name='estado_sesion'),
    path('sesion/cerrar/', views.cerrar_sesion_cliente, name='cerrar_sesion_cliente'),

    # ── Pago en línea (cliente) ─────────────────────────────────────────────────
    # Flujo PayPal "redirect" (misma pestaña, fix 1.7):
    #   crear/   — POST JSON: crea la orden y devuelve approve_url (cliente redirige).
    #   capturar/— POST JSON legacy (compatibilidad con SDK Buttons / tests).
    #   retorno/ — GET: PayPal redirige aquí tras aprobar; captura y vuelve a pedidos.
    #   cancelar/— GET: PayPal redirige aquí si el cliente cancela en la pasarela.
    path('pago/desglose/',        views.desglose_pago,              name='desglose_pago'),
    path('pago/paypal/crear/',    views.paypal_crear_orden_cliente, name='paypal_crear_orden'),
    path('pago/paypal/capturar/', views.paypal_capturar_cliente,    name='paypal_capturar'),
    path('pago/paypal/retorno/',  views.paypal_retorno_cliente,     name='paypal_retorno'),
    path('pago/paypal/cancelar/', views.paypal_cancelar_cliente,    name='paypal_cancelar'),

    # ── Ticket PDF (cliente) ────────────────────────────────────────────────────
    # 1.8: el cliente abre el mismo PDF que el mesero, con el mismo layout.
    path('ticket/<int:solicitud_id>/pdf/', views.ticket_pdf_cliente, name='ticket_pdf'),
]
