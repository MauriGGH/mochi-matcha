"""
Rutas URL del módulo mesero (namespace 'mesero').

Todas las rutas están bajo el prefijo /mesero/ definido en el urls.py raíz.
Las vistas están protegidas por el decorador @mesero_requerido excepto
login_mesero y logout_mesero, que se encargan de la autenticación.

Grupos de rutas:
  - Autenticación:   login, logout.
  - Mapa de mesas:   mapa principal (HTML), estado en tiempo real (JSON GET),
                     detalle de mesa (JSON GET).
  - Pedidos:         pedidos listos, entregar, cancelar, editar.
  - Sesiones/Mesas:  cerrar sesión individual, cerrar mesa completa,
                     agregar sesión asistida.
  - Pedido asistido: formulario GET y confirmación POST.
  - Alertas/Cuentas: listado de alertas, marcar atendida, solicitar cuenta,
                     cancelar solicitud de cobro.
  - Pago:            formulario de cobro, procesar pago, total en vivo.
  - PayPal:          crear orden, capturar orden aprobada.
  - Ticket:          ver ticket HTML, descargar PDF.
  - Alias:           /mesas/ → mapa_mesas, /productos/json/ → catálogo JSON.
"""

from django.urls import path
from . import views

app_name = 'mesero'

urlpatterns = [
    # ── Autenticación ─────────────────────────────────────────────────────────
    path('login/',                        views.login_mesero,              name='login_mesero'),
    path('logout/',                       views.logout_mesero,             name='logout_mesero'),

    # ── Mapa de mesas ─────────────────────────────────────────────────────────
    path('mapa/',                         views.mapa_mesas,                name='mapa_mesas'),
    # Endpoint de polling JSON para actualizar los tiles del mapa cada 3 s
    path('mapa/estado/',                  views.mesas_estado,              name='mesas_estado'),
    # Detalle de una mesa individual para el panel lateral (JSON GET)
    path('mapa/<int:mesa_id>/',           views.detalle_mesa,              name='detalle_mesa'),

    # ── Pedidos ───────────────────────────────────────────────────────────────
    path('pedidos-listos/',               views.pedidos_listos,            name='pedidos_listos'),
    path('pedidos-listos/json/',          views.pedidos_listos_json,       name='pedidos_listos_json'),
    path('pedidos/entregar/',             views.entregar_pedido,           name='entregar_pedido'),
    path('pedidos/cancelar/',             views.cancelar_pedido,           name='cancelar_pedido'),
    # Solo pedidos en estado 'recibido' pueden editarse (GET → datos, POST → cambios)
    path('pedidos/<int:pedido_id>/editar/', views.editar_pedido_mesero,    name='editar_pedido_mesero'),

    # ── Sesiones y mesas ──────────────────────────────────────────────────────
    path('sesion/cerrar/',                views.cerrar_sesion,             name='cerrar_sesion'),
    path('mesa/cerrar/',                  views.cerrar_mesa,               name='cerrar_mesa'),

    # ── Pedido asistido ───────────────────────────────────────────────────────
    # GET: abre el modal de pedido asistido; POST: confirma y envía a cocina
    path('asistido/',                     views.pedido_asistido,           name='pedido_asistido'),
    path('asistido/confirmar/',           views.confirmar_pedido_asistido, name='confirmar_pedido_asistido'),

    # ── Alertas y cuentas ─────────────────────────────────────────────────────
    path('alertas/',                      views.alertas,                   name='alertas'),
    path('alertas/atender/',              views.atender_alerta,            name='atender_alerta'),
    path('alertas/limpiar/',              views.limpiar_notificaciones,    name='limpiar_notificaciones'),
    # /cuentas/ es alias semántico de /alertas/ enfocado en solicitudes de cobro
    path('cuentas/',                      views.cuentas,                   name='cuentas'),
    path('cuentas/solicitar/',            views.solicitar_cuenta_mesero,   name='solicitar_cuenta_mesero'),
    path('cuentas/cancelar/',             views.cancelar_solicitud_pago,   name='cancelar_solicitud_pago'),
    # Agrega un cliente a una mesa ya ocupada sin que ese cliente escanee QR
    path('sesion/agregar/',               views.agregar_sesion_asistida,   name='agregar_sesion_asistida'),

    # Pago
    path('pago/',                         views.pago,                      name='pago'),
    path('pago/procesar/',                views.procesar_pago,             name='procesar_pago'),
    # Recalcula el total en vivo desde la BD al abrir el modal de cobro (P2)
    path('pago/total/',                   views.total_cobro,               name='total_cobro'),

    # PayPal
    # Paso 1: el JS llama a crear-orden para obtener el order_id de PayPal
    path('paypal/crear-orden/',           views.paypal_crear_orden,        name='paypal_crear_orden'),
    # Paso 2: tras la aprobación del cliente, el JS llama a capturar para
    # cobrar y registrar el pago en la BD
    path('paypal/capturar/',              views.paypal_capturar,           name='paypal_capturar'),

    # Ticket
    path('ticket/<int:solicitud_id>/',    views.ver_ticket,                name='ver_ticket'),
    path('ticket/<int:solicitud_id>/pdf/', views.ticket_pdf,               name='ticket_pdf'),

    # Alias
    path('mesas/',                        views.mapa_mesas,                name='mesas'),
    # Catálogo de productos disponibles en JSON, usado por el modal asistido
    path('productos/json/',               views.productos_json,            name='productos_json'),
]
