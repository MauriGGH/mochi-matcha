"""
cliente/views.py — Vistas para el módulo de cliente (sin autenticación Django).
"""
import json
import uuid
import random
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone

from apps.accounts.decorators import sesion_cliente_requerida
from apps.mesas.models import Mesa, SesionCliente
from apps.menu.models import Categoria, Producto, Promocion
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador
from apps.catalogs.models import ModalidadIngreso


def _get_carrito(request):
    """Devuelve la lista de ítems del carrito almacenada en la sesión Django, o [] si vacía."""
    return request.session.get("carrito", [])

def _save_carrito(request, carrito):
    """
    Persiste la lista de ítems en la sesión Django.
    Marca modified=True explícitamente porque la sesión contiene un objeto mutable
    (lista) y Django no detecta cambios internos automáticamente.
    """
    request.session["carrito"] = carrito
    request.session.modified = True

def _sesion_activa_o_error(request):
    """
    Devuelve None si la sesión está activa; si ya fue pagada/cerrada devuelve
    un JsonResponse 409. Evita que el cliente modifique el carrito de una
    cuenta ya saldada (P6).
    """
    sesion = request.sesion_cliente
    if sesion and sesion.estado != "activa":
        return JsonResponse({
            "ok": False,
            "error": "Tu cuenta ya fue cerrada. No puedes modificar el pedido.",
            "sesion_pagada": True,
        }, status=409)
    return None

def _generar_pin():
    """Genera un PIN numérico de 4 dígitos."""
    return str(random.randint(1000, 9999))


# ─── Estado público de mesa (sin auth) ────────────────────────────────────────

def estado_mesa(request, mesa_id):
    """
    GET /bienvenida/estado/<mesa_id>/
    Devuelve estado de la mesa y alias activos para el flujo de recuperación.
    """
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    sesiones = mesa.sesiones.filter(estado="activa").values_list("alias", flat=True)
    return JsonResponse({
        "ok": True,
        "numero_mesa": mesa.numero_mesa,
        "estado": mesa.estado,
        # FIX: PIN eliminado del endpoint público
        "sesiones_activas": list(sesiones),
        "count": len(sesiones),
    })


# ─── Bienvenida ───────────────────────────────────────────────────────────────

def bienvenida(request):
    """
    GET — pantalla de bienvenida del cliente.

    Acepta el parámetro ?mesa=<id> (desde el QR de la mesa) o lo recupera de la
    sesión Django si el cliente ya pasó por aquí antes. El parámetro ?step controla
    qué sub-paso del wizard de bienvenida se renderiza (nuevo, recuperar, pin_generado).
    Si la mesa tiene sesiones "pagada" pendientes de cierre por el mesero, muestra
    el paso "mesa_cerrando" para impedir el ingreso de nuevos comensales.
    """
    mesa_id = request.GET.get("mesa") or request.session.get("mesa_id")
    if not mesa_id:
        return render(request, "cliente/bienvenida.html", {"error_mesa": True})
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    step = request.GET.get("step", "")
    sesiones_activas = mesa.sesiones.filter(estado="activa").count()

    # Bloquear ingreso si la mesa está en proceso de cierre:
    # cubre dos casos: (a) sesiones pagadas aún no cerradas por el mesero,
    # (b) nota_cierre seteada aunque las sesiones sigan activas (pago parcial).
    # Se aplica SIEMPRE, incluso si el cliente pasa ?step=nuevo en la URL.
    # Excepción: step=recuperar permite a clientes existentes recuperar su sesión.
    _en_cierre = mesa.estado != "libre" and (
        bool(mesa.nota_cierre) or
        mesa.sesiones.filter(estado="pagada").exists()
    )
    if _en_cierre and step != "recuperar":
        step = "mesa_cerrando"

    return render(request, "cliente/bienvenida.html", {
        "mesa": mesa, "step": step, "sesiones_activas": sesiones_activas,
    })


@require_POST
def crear_sesion(request, mesa_id):
    """
    POST — crea una nueva SesionCliente para el alias indicado en la mesa dada.

    Si es el primer cliente de la mesa genera un PIN de 4 dígitos y marca la mesa
    como "ocupada". Si ya existen sesiones activas, reutiliza el PIN vigente.
    Al finalizar, redirige al cliente a la pantalla del PIN (primer cliente) o
    directamente al menú, y establece la cookie mm_session.

    Parámetros POST:
        alias     -- nombre que el cliente elige para identificarse en la mesa.
        modalidad -- modalidad de ingreso (por defecto "qr").
    """
    from django.db import transaction
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    alias = request.POST.get("alias", "").strip()[:50]
    modalidad_str = request.POST.get("modalidad", "qr")

    if not alias:
        return redirect(f"/bienvenida/?mesa={mesa_id}")

    # Bloquear creación si la mesa está en proceso de cierre:
    # (a) sesiones pagadas pendientes de cerrar, o (b) nota_cierre seteada.
    if mesa.estado != "libre" and (
        bool(mesa.nota_cierre) or mesa.sesiones.filter(estado="pagada").exists()
    ):
        return render(request, "cliente/bienvenida.html", {
            "mesa": mesa, "step": "mesa_cerrando",
            "sesiones_activas": mesa.sesiones.filter(estado="activa").count(),
        })

    if SesionCliente.objects.filter(mesa=mesa, alias=alias, estado="activa").exists():
        return render(request, "cliente/bienvenida.html", {
            "mesa": mesa, "step": "nuevo",
            "sesiones_activas": mesa.sesiones.filter(estado="activa").count(),
            "error": "Ese alias ya está en uso en esta mesa. Elige otro.",
        })

    modalidad, _ = ModalidadIngreso.objects.get_or_create(descripcion=modalidad_str)
    token = uuid.uuid4().hex

    # P3: bloquear la mesa con select_for_update. Sin esto, dos clientes "nuevos"
    # simultáneos evaluaban es_primer_cliente=True a la vez y ambos generaban un
    # PIN distinto — el segundo pisaba al primero y lo dejaba sin acceso.
    with transaction.atomic():
        mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
        # Re-verificar dentro de la transacción para evitar race condition.
        # Recargar nota_cierre desde BD (select_for_update ya bloqueó la fila).
        if mesa.estado != "libre" and (
            bool(mesa.nota_cierre) or mesa.sesiones.filter(estado="pagada").exists()
        ):
            return render(request, "cliente/bienvenida.html", {
                "mesa": mesa, "step": "mesa_cerrando",
                "sesiones_activas": mesa.sesiones.filter(estado="activa").count(),
            })
        es_primer_cliente = not mesa.sesiones.filter(estado="activa").exists()
        if es_primer_cliente or not mesa.pin_actual:
            mesa.pin_actual = _generar_pin()
            mesa.estado = "ocupada"
            mesa.save(update_fields=["pin_actual", "estado"])
        elif mesa.estado == "libre":
            mesa.estado = "ocupada"
            mesa.save(update_fields=["estado"])

        SesionCliente.objects.create(
            alias=alias, token_cookie=token, estado="activa",
            mesa=mesa, modalidad_ingreso=modalidad,
        )

    request.session["mesa_id"] = mesa_id
    request.session["alias"] = alias
    request.session["pin_mesa"] = mesa.pin_actual

    response = redirect("cliente:menu")
    # Solo el primer cliente de la mesa ve la pantalla de PIN para que pueda
    # compartirlo con quienes deseen unirse desde el mismo dispositivo.
    # Pasar PIN al template de confirmación si es primer cliente
    if es_primer_cliente:
        response = redirect(f"/bienvenida/pin/?mesa={mesa_id}&alias={alias}")
    response.set_cookie("mm_session", token, max_age=7200, httponly=True, samesite="Lax")
    return response


def mostrar_pin(request):
    """GET — pantalla intermedia que muestra el PIN generado al primer cliente."""
    mesa_id = request.GET.get("mesa") or request.session.get("mesa_id")
    alias = request.GET.get("alias") or request.session.get("alias")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None
    pin = request.session.get("pin_mesa") or (mesa.pin_actual if mesa else None)
    return render(request, "cliente/bienvenida.html", {
        "mesa": mesa, "step": "pin_generado",
        "pin": pin, "alias": alias,
    })


@require_POST
def recuperar_sesion(request, mesa_id):
    """POST — recupera sesión validando alias + PIN de mesa."""
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    alias = request.POST.get("alias", "").strip()
    pin = request.POST.get("pin", "").strip()

    # Validar PIN
    if mesa.pin_actual != pin:
        sesiones_activas = mesa.sesiones.filter(estado="activa").count()
        return render(request, "cliente/bienvenida.html", {
            "mesa": mesa, "step": "recuperar",
            "sesiones_activas": sesiones_activas,
            "error": "PIN incorrecto. Pide el PIN a quien creó la sesión de mesa.",
            "alias_previo": alias,
        })

    try:
        sesion = SesionCliente.objects.get(mesa=mesa, alias=alias, estado="activa")
    except SesionCliente.DoesNotExist:
        sesiones_activas = mesa.sesiones.filter(estado="activa").count()
        return render(request, "cliente/bienvenida.html", {
            "mesa": mesa, "step": "recuperar",
            "sesiones_activas": sesiones_activas,
            "error": "No encontramos ese alias en esta mesa.",
            "alias_previo": alias,
        })

    request.session["mesa_id"] = mesa_id
    request.session["alias"] = alias
    request.session["pin_mesa"] = mesa.pin_actual

    response = redirect("cliente:menu")
    response.set_cookie("mm_session", sesion.token_cookie, max_age=7200, httponly=True, samesite="Lax")
    return response


# ─── Menú ─────────────────────────────────────────────────────────────────────

@sesion_cliente_requerida
def menu(request):
    """
    GET — renderiza el menú de productos para el cliente autenticado.

    Carga todas las categorías con sus productos disponibles (prefetch de modificadores
    activos) y las promociones vigentes para hoy. Pasa al template el carrito actual,
    datos de sesión/mesa y el listado de promos activas para el carrusel.
    """
    from django.utils import timezone
    from django.db.models import Prefetch
    from apps.menu.models import OpcionModificador as _Opcion
    categorias = list(Categoria.objects.prefetch_related(
        Prefetch(
            "productos__grupos_modificadores__opciones",
            queryset=_Opcion.objects.filter(activo=True),
        )
    ).all())
    for cat in categorias:
        cat.productos_disponibles = [p for p in cat.productos.all() if p.disponible]

    # Promociones activas para carrusel — solo las que aplican hoy
    promos_activas = [
        p for p in Promocion.objects.filter(activa=True)
        .prefetch_related('productos_aplicables')
        .order_by('orden', '-fecha_inicio')
        if p.aplica_hoy()
    ]
    # Compatibilidad: mantener promo_banner apuntando a la primera (por si hay código que lo usa)
    promo_banner = promos_activas[0] if promos_activas else None

    carrito = _get_carrito(request)
    sesion = request.sesion_cliente
    return render(request, "cliente/menu.html", {
        "categorias": categorias,
        "carrito_count": len(carrito),
        "sesion": sesion,
        "mesa": sesion.mesa,
        "pin_mesa": sesion.mesa.pin_actual,
        "promo_banner": promo_banner,
        "promos_activas": promos_activas,
    })


# ─── Carrito ──────────────────────────────────────────────────────────────────

@sesion_cliente_requerida
def carrito(request):
    """
    GET — renderiza la vista del carrito del cliente.

    Serializa los ítems a JSON (carrito_json) para que el JavaScript del frontend
    pueda rehidratar el estado sin recargar la página.
    """
    import json as _json
    items = _get_carrito(request)
    total = sum(item.get("subtotal", 0) for item in items)
    sesion = request.sesion_cliente
    carrito_json = _json.dumps([
        {
            "producto_id": i.get("producto_id"),
            "cantidad": i.get("cantidad", 1),
            "subtotal": float(i.get("subtotal", 0)),
            "modificadores": i.get("modificadores", []),
            "notas": i.get("notas", ""),
        }
        for i in items
    ])
    return render(request, "cliente/carrito.html", {
        "carrito": items, "total": total,
        "carrito_count": len(items), "sesion": sesion,
        "mesa": sesion.mesa, "pin_mesa": sesion.mesa.pin_actual,
        "carrito_json": carrito_json,
    })


@require_POST
@sesion_cliente_requerida
def agregar_carrito(request):
    """
    POST JSON — agrega un producto al carrito de la sesión.

    Calcula el subtotal sumando el precio base del producto más el precio extra
    de cada modificador seleccionado, multiplicado por la cantidad.

    Body JSON:
        producto_id    -- PK del Producto (debe estar disponible).
        cantidad       -- unidades a agregar (por defecto 1).
        modificadores  -- lista de PKs de OpcionModificador.
        notas          -- texto libre con instrucciones para cocina.

    Retorna JSON: {ok, carrito_count}
    """
    bloqueo = _sesion_activa_o_error(request)
    if bloqueo:
        return bloqueo
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    producto_id = data.get("producto_id")
    cantidad = int(data.get("cantidad", 1))
    modificadores_ids = data.get("modificadores", [])
    notas = data.get("notas", "")
    producto = get_object_or_404(Producto, pk=producto_id, disponible=True)
    from apps.menu.models import OpcionModificador
    precio_extra = 0
    opciones_detalle = []
    if modificadores_ids:
        for op in OpcionModificador.objects.filter(pk__in=modificadores_ids):
            precio_extra += float(op.precio_extra)
            opciones_detalle.append({"id": op.pk, "nombre": op.nombre_opcion, "extra": float(op.precio_extra)})
    subtotal = (float(producto.precio) + precio_extra) * cantidad
    items = _get_carrito(request)
    items.append({
        "producto_id": producto.pk, "nombre": producto.nombre,
        "precio_unitario": float(producto.precio), "cantidad": cantidad,
        "modificadores": opciones_detalle, "notas": notas, "subtotal": subtotal,
    })
    _save_carrito(request, items)
    return JsonResponse({"ok": True, "carrito_count": len(items)})


@require_POST
@sesion_cliente_requerida
def actualizar_carrito(request):
    """
    POST JSON — actualiza la cantidad de un ítem del carrito por índice.

    Si la nueva cantidad es <= 0, elimina el ítem. Recalcula el subtotal del
    ítem afectado considerando sus modificadores.

    Body JSON:
        index    -- posición del ítem en la lista del carrito.
        cantidad -- nueva cantidad deseada (0 o negativo para eliminar).

    Retorna JSON: {ok, carrito_count, total}
    """
    bloqueo = _sesion_activa_o_error(request)
    if bloqueo:
        return bloqueo
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    index = data.get("index")
    cantidad = int(data.get("cantidad", 1))
    items = _get_carrito(request)
    if index is None or not (0 <= index < len(items)):
        return JsonResponse({"ok": False, "error": "Índice inválido"}, status=400)
    if cantidad <= 0:
        items.pop(index)
    else:
        item = items[index]
        precio_extras = sum(op["extra"] for op in item.get("modificadores", []))
        item["cantidad"] = cantidad
        item["subtotal"] = (item["precio_unitario"] + precio_extras) * cantidad
        items[index] = item
    _save_carrito(request, items)
    total = sum(i.get("subtotal", 0) for i in items)
    return JsonResponse({"ok": True, "carrito_count": len(items), "total": total})


@require_POST
@sesion_cliente_requerida
def eliminar_carrito(request):
    """
    POST JSON — elimina un ítem del carrito por índice, sin verificar estado de sesión.

    A diferencia de actualizar_carrito, esta vista permite eliminar ítems incluso
    cuando la sesión ya no está activa (p.ej., el cliente revisa su ticket y quiere
    limpiar manualmente). Retorna JSON: {ok, carrito_count, total}.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    index = data.get("index")
    items = _get_carrito(request)
    if index is None or not (0 <= index < len(items)):
        return JsonResponse({"ok": False, "error": "Índice inválido"}, status=400)
    items.pop(index)
    _save_carrito(request, items)
    total = sum(i.get("subtotal", 0) for i in items)
    return JsonResponse({"ok": True, "carrito_count": len(items), "total": total})


@require_POST
@sesion_cliente_requerida
def limpiar_carrito(request):
    """POST — vacía el carrito por completo. Útil para empezar un nuevo pedido."""
    _save_carrito(request, [])
    return JsonResponse({"ok": True})


@require_POST
@sesion_cliente_requerida
def confirmar_pedido(request):
    """
    POST — convierte el carrito en un Pedido persistido en base de datos.

    Aplica las promociones elegibles antes de crear el pedido. Usa select_for_update
    sobre la SesionCliente para garantizar que la sesión sigue activa dentro de la
    transacción y evitar pedidos sobre cuentas ya cobradas. Implementa idempotencia
    mediante token_idempotencia: si el cliente reintenta (doble-click, reconexión),
    se devuelve el pedido existente sin crear uno nuevo.

    Body JSON (opcional):
        promocion_id    -- PK de la Promocion preferida si hay varias elegibles.
        idempotency_key -- token UUID generado en el frontend por intento.

    Retorna JSON: {ok, pedido_id} o {ok, pedido_id, duplicado: True} si ya existía.
    """
    from django.db import transaction
    from apps.pedidos.utils import aplicar_promociones
    from apps.mesas.models import SesionCliente
    from apps.cliente.rate_limit import check_confirmar_pedido
    items = _get_carrito(request)
    if not items:
        return JsonResponse({"ok": False, "error": "El carrito está vacío"}, status=400)
    sesion = request.sesion_cliente
    # 2.3: corta ráfagas de pedidos (máx 5 en 60 s por sesión).
    blocked = check_confirmar_pedido(sesion.pk)
    if blocked:
        return blocked
    from apps.menu.models import OpcionModificador

    # El cliente puede haber elegido una promo concreta (cuando hay varias elegibles)
    # y envía un token de idempotencia por intento de confirmación.
    promo_seleccionada = request.POST.get("promocion_id") or None
    idempotency_key = None
    try:
        body = json.loads(request.body or "{}")
        if not promo_seleccionada:
            promo_seleccionada = body.get("promocion_id")
        idempotency_key = body.get("idempotency_key") or None
    except (ValueError, TypeError):
        pass

    # Aplicar promociones (regla: máximo una por pedido)
    items, promos_aplicadas, _elegibles = aplicar_promociones(
        items, sesion, promocion_id=promo_seleccionada
    )

    # REFUERZO INTEGRIDAD (P1): bloquear la sesión con select_for_update y
    # re-validar que siga "activa" DENTRO de la transacción. La idempotencia por
    # token (token_idempotencia, único en BD) garantiza que un doble-click o
    # dos requests concurrentes NO creen dos pedidos: la 2ª choca con el token
    # ya usado y devuelve el pedido existente.
    with transaction.atomic():
        sesion_locked = (
            SesionCliente.objects
            .select_for_update()
            .filter(pk=sesion.pk)
            .first()
        )
        if sesion_locked is None or sesion_locked.estado != "activa":
            return JsonResponse({
                "ok": False,
                "error": "Tu cuenta ya fue cerrada. No puedes agregar más pedidos.",
                "sesion_pagada": True,
            }, status=409)

        # Idempotencia: si ya existe un pedido con este token, devolverlo sin
        # crear uno nuevo (el cliente reintentó / hizo doble-click).
        if idempotency_key:
            ya_existe = Pedido.objects.filter(token_idempotencia=idempotency_key).first()
            if ya_existe is not None:
                _save_carrito(request, [])
                return JsonResponse({"ok": True, "pedido_id": ya_existe.pk, "duplicado": True})

        # Re-leer el carrito dentro del lock: si otra request concurrente ya lo
        # procesó, estará vacío y no duplicamos el pedido.
        items_actuales = _get_carrito(request)
        if not items_actuales:
            return JsonResponse({"ok": False, "error": "El carrito está vacío"}, status=400)

        pedido = Pedido.objects.create(
            sesion=sesion_locked, modalidad=sesion_locked.modalidad_ingreso,
            token_idempotencia=idempotency_key or None,
        )
        for item in items:
            producto = get_object_or_404(Producto, pk=item["producto_id"])
            detalle = DetallePedido.objects.create(
                pedido=pedido, producto=producto, cantidad=item["cantidad"],
                notas=item.get("notas", ""), subtotal_calculado=item["subtotal"],
                promocion_id=item.get("promocion_id"),
            )
            for op_data in item.get("modificadores", []):
                try:
                    opcion = OpcionModificador.objects.get(pk=op_data["id"])
                    DetalleModificador.objects.create(
                        detalle=detalle, opcion=opcion,
                        precio_extra_aplicado=op_data["extra"],
                        nombre_opcion_historico=opcion.nombre_opcion,  # snapshot
                    )
                except OpcionModificador.DoesNotExist:
                    # Si la opción fue eliminada del catálogo entre que el cliente
                    # la agregó y confirmó, se omite silenciosamente para no bloquear
                    # el pedido completo por un modificador inválido.
                    pass
        _save_carrito(request, [])
    return JsonResponse({"ok": True, "pedido_id": pedido.pk})


# ─── Pedidos ──────────────────────────────────────────────────────────────────

@sesion_cliente_requerida
def pedidos(request):
    """
    GET — vista del historial de pedidos del cliente y punto de entrada al pago en línea.

    Calcula el total general sumando los subtotales de todos los detalles de la sesión.
    Carga la configuración de PayPal (client_id y modo) para que el template pueda
    inicializar el SDK de PayPal en el navegador si el cliente desea pagar en línea.
    """
    sesion = request.sesion_cliente
    mis_pedidos = sesion.pedidos.prefetch_related(
        "detalles__producto", "detalles__modificadores__opcion"
    ).order_by("-fecha_hora_ingreso")
    total_general = sum(
        sum(d.subtotal_calculado for d in p.detalles.all()) for p in mis_pedidos
    )
    # Total de TODA la mesa (todas las sesiones activas) para la opción de pago
    # grupal vía PayPal — necesario para previsualizar propinas en porcentaje (1.6).
    from django.db.models import Sum as _Sum
    sesiones_activas_mesa = sesion.mesa.sesiones.filter(estado="activa")
    total_mesa = DetallePedido.objects.filter(
        pedido__sesion__in=sesiones_activas_mesa
    ).exclude(pedido__estado="cancelado").aggregate(
        t=_Sum("subtotal_calculado"),
    )["t"] or 0
    from apps.mesero.views import _paypal_cfg
    paypal_client_id = _paypal_cfg("paypal_client_id")
    paypal_modo      = _paypal_cfg("paypal_modo", "sandbox")

    # 1.3/1.7: tras volver del flujo redirect de PayPal, recogemos (one-shot) el
    # ticket o el mensaje de error/cancelación que dejó el handler en la sesión
    # Django. Pre-serializamos a JSON aquí (no dejamos que Django lo renderice
    # con repr()) para que el template pueda inyectarlo en una constante JS.
    paypal_ticket_dict = request.session.pop("paypal_ticket_inicial", None)
    paypal_error_msg   = request.session.pop("paypal_error_msg", None)
    paypal_ticket_json = json.dumps(paypal_ticket_dict) if paypal_ticket_dict else "null"
    paypal_ok          = request.GET.get("paypal_ok") == "1"
    paypal_cancelado   = request.GET.get("paypal_cancelado") == "1"
    paypal_error       = request.GET.get("paypal_error") == "1"
    if paypal_ticket_dict or paypal_error_msg:
        request.session.modified = True

    return render(request, "cliente/pedidos.html", {
        "pedidos": mis_pedidos, "total_general": total_general,
        "total_mesa": total_mesa,
        "carrito_count": len(_get_carrito(request)),
        "sesion": sesion, "mesa": sesion.mesa, "pin_mesa": sesion.mesa.pin_actual,
        "paypal_client_id": paypal_client_id,
        "paypal_modo": paypal_modo,
        "paypal_ticket_inicial_json": paypal_ticket_json,
        "paypal_error_msg": paypal_error_msg,
        "paypal_ok": paypal_ok,
        "paypal_cancelado": paypal_cancelado,
        "paypal_error": paypal_error,
    })


@require_GET
@sesion_cliente_requerida
def estado_pedidos(request):
    """
    GET — endpoint de polling que devuelve el estado de todos los pedidos de la sesión.

    Retorna también sesion_estado para que el frontend detecte cuando el mesero
    cobra la cuenta y pueda redirigir al cliente a la pantalla de pago completado.
    El campo ts (timestamp en ms) permite al cliente descartar respuestas antiguas.
    """
    sesion = request.sesion_cliente
    data = []
    for p in sesion.pedidos.prefetch_related("detalles__producto").order_by("-fecha_hora_ingreso"):
        data.append({
            "id": p.pk, "estado": p.estado,
            "estado_display": p.get_estado_display(),
            "fecha": p.fecha_hora_ingreso.strftime("%H:%M"),
            "items": [{"nombre": d.producto.nombre, "cantidad": d.cantidad} for d in p.detalles.all()],
        })
    # Incluir el estado de la sesión para que el polling del cliente detecte
    # cuando la cuenta fue saldada (problema 2: ya no se expulsa al cliente).
    return JsonResponse({
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "pedidos": data,
        "sesion_estado": sesion.estado,
    })


@require_POST
@sesion_cliente_requerida
def solicitar_ayuda(request):
    """
    POST JSON — crea una AlertaMesero de tipo "ayuda" para la mesa del cliente.

    Permite al cliente llamar al mesero desde la app sin levantarse. El mensaje
    opcional del body reemplaza el texto genérico de la alerta.

    Body JSON (opcional):
        mensaje -- texto libre con la petición (por defecto "El cliente solicita atención.").

    Retorna JSON: {ok, mensaje}
    """
    if not request.sesion_cliente:
        return JsonResponse({"ok": False, "error": "Sesión no válida"}, status=401)
    sesion = request.sesion_cliente
    from apps.mesas.models import AlertaMesero
    from apps.cliente.rate_limit import check_solicitar_ayuda
    # 2.3: máx 1 alerta cada 30 s y 3 sin atender vivas simultáneamente.
    alertas_vivas = AlertaMesero.objects.filter(sesion=sesion, atendida=False).count()
    blocked = check_solicitar_ayuda(sesion.pk, alertas_vivas)
    if blocked:
        return blocked
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}
    mensaje = data.get("mensaje", "El cliente solicita atención.")
    AlertaMesero.objects.create(
        mesa=sesion.mesa,
        sesion=sesion,
        tipo="ayuda",
        mensaje=mensaje,
    )
    return JsonResponse({"ok": True, "mensaje": "Se ha notificado a tu mesero."})


@require_POST
@sesion_cliente_requerida
def solicitar_cuenta(request):
    """
    POST JSON — solicita el cobro de la cuenta al mesero (individual o grupal).

    Crea una SolicitudPago en estado "pendiente" y una AlertaMesero de tipo "cuenta".
    Usa get_or_create para idempotencia: múltiples pulsaciones del botón no generan
    solicitudes duplicadas. En modo grupal bloquea la mesa con select_for_update para
    serializar solicitudes concurrentes de distintos comensales.

    Body JSON:
        tipo             -- "individual" (solo esta sesión) o "grupal" (toda la mesa).
        metodo_preferido -- "EFECTIVO" o "TARJETA" (opcional, informativo para el mesero).

    Retorna JSON: {ok, mensaje}
    """
    if not request.sesion_cliente:
        return JsonResponse({"ok": False, "error": "Sesión no válida"}, status=401)
    sesion = request.sesion_cliente

    # BUGFIX (problema 1): si la sesión ya fue pagada/cerrada, no se puede
    # volver a solicitar la cuenta. Esto cierra la puerta a "pagar de nuevo".
    if sesion.estado != "activa":
        return JsonResponse({
            "ok": False,
            "error": "Esta cuenta ya fue saldada.",
            "sesion_pagada": True,
        }, status=409)

    # 2.3: cooldown de 30 s entre solicitudes de cuenta. La idempotencia
    # de get_or_create permite re-pulsar el botón sin penalización (no se
    # crea una segunda fila); este cooldown frena el patrón abusivo de
    # cancelar y re-solicitar en bucle.
    from apps.cliente.rate_limit import check_solicitar_cuenta
    blocked = check_solicitar_cuenta(sesion.pk)
    if blocked:
        return blocked

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}
    tipo = data.get("tipo", "individual")
    confirmar_sin_entrega = bool(data.get("confirmar_sin_entrega", False))

    from apps.pedidos.models import SolicitudPago, Pedido as _Pedido
    from apps.catalogs.models import EstadoSolicitud
    from django.db import transaction

    # Verificar si hay pedidos aún no entregados. Si los hay y el cliente no
    # confirmó explícitamente, devolver aviso (sin bloquear: el cliente decide).
    if not confirmar_sin_entrega:
        if tipo == "grupal":
            pedidos_pendientes = _Pedido.objects.filter(
                sesion__mesa=sesion.mesa,
                sesion__estado="activa",
                estado__in=("recibido", "preparando", "listo"),
            ).exclude(estado="cancelado").count()
        else:
            pedidos_pendientes = sesion.pedidos.filter(
                estado__in=("recibido", "preparando", "listo"),
            ).exclude(estado="cancelado").count()

        if pedidos_pendientes > 0:
            return JsonResponse({
                "ok": False,
                "requiere_confirmacion": True,
                "pedidos_pendientes": pedidos_pendientes,
                "error": (
                    f"Tienes {pedidos_pendientes} pedido(s) que aún no han sido entregados. "
                    "¿Deseas solicitar la cuenta de todas formas?"
                ),
            }, status=200)

    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")

    # FIX: calcular totales reales
    pedidos_sesion = sesion.pedidos.prefetch_related("detalles").exclude(estado="cancelado")
    total_individual = sum(
        sum(d.subtotal_calculado for d in p.detalles.all()) for p in pedidos_sesion
    )
    total_mesa = None
    if tipo == "grupal":
        total_mesa = sum(
            sum(d.subtotal_calculado for d in p.detalles.all())
            for s in sesion.mesa.sesiones.filter(estado="activa")
            for p in s.pedidos.prefetch_related("detalles").exclude(estado="cancelado")
        )

    # FIX: idempotencia — no crear duplicados
    metodo_preferido = data.get("metodo_preferido", "").strip().upper()
    detalle = metodo_preferido if metodo_preferido in ("EFECTIVO", "TARJETA") else ""

    metodo_label = {"EFECTIVO": "efectivo", "TARJETA": "tarjeta"}.get(detalle, "")
    mensaje_alerta = f"Solicitud de cuenta ({metodo_label})" if metodo_label else "Solicitud de cuenta"

    with transaction.atomic():
        if tipo == "grupal":
            # BUGFIX (problema 1 y 3): una solicitud GRUPAL es de la MESA, no de
            # una sesión concreta. Si se guarda con sesion=<solicitante>, el
            # mesero la cobra como individual (cierra una sola sesión) y el panel
            # muestra total_individual en vez de total_mesa (se "pierden"
            # productos de las otras sesiones). Por eso: sesion=None y
            # total_individual=None — solo total_mesa es la fuente de verdad.
            #
            # P4: bloquear la mesa serializa las solicitudes grupales concurrentes
            # de dos clientes — así NO se crean dos SolicitudPago grupales
            # pendientes (que harían fallar el cobro con MultipleObjectsReturned).
            from apps.mesas.models import Mesa as _Mesa
            _Mesa.objects.select_for_update().get(pk=sesion.mesa_id)
            sol, created = SolicitudPago.objects.get_or_create(
                mesa=sesion.mesa,
                sesion=None,
                tipo="grupal",
                estado_solicitud=estado_pendiente,
                defaults={
                    "total_mesa": total_mesa,
                    "propina_sugerida": round((total_mesa or 0) * 10 / 100, 2),
                    "detalle_pago": detalle,
                },
            )
        else:
            sol, created = SolicitudPago.objects.get_or_create(
                sesion=sesion,
                tipo="individual",
                estado_solicitud=estado_pendiente,
                defaults={
                    "mesa": sesion.mesa,
                    "total_individual": total_individual,
                    "propina_sugerida": round(total_individual * 10 / 100, 2),
                    "detalle_pago": detalle,
                },
            )
        if created:
            from apps.mesas.models import AlertaMesero
            AlertaMesero.objects.create(
                mesa=sesion.mesa,
                sesion=sesion,
                tipo="cuenta",
                mensaje=mensaje_alerta,
            )
    return JsonResponse({"ok": True, "mensaje": "Tu mesero se acercará en breve."})


# ─── PayPal (cliente paga en línea) ───────────────────────────────────────────
#
# Flujo "redirect" (misma pestaña — fix 1.7):
#   1. Cliente pulsa "Pagar con PayPal" en pedidos.html → POST a
#      paypal_crear_orden_cliente con tipo + propina opcional.
#   2. El backend crea la orden en PayPal incluyendo propina y devuelve el
#      `approve_url` de PayPal + las URLs return/cancel. El JS hace
#      `window.location.href = approve_url`, redirigiendo la pestaña actual.
#   3. Cliente aprueba en paypal.com. PayPal redirige a `paypal_retorno_cliente`
#      con ?token=<order_id>. El backend hace capture, marca la sesión como
#      pagada y vuelve a /cliente/pedidos/?paypal_ok=1 con el ticket guardado
#      en la sesión Django (one-shot).
#   4. pedidos.html lee `paypal_ticket_inicial` y muestra el modal unificado
#      `cuentaPagadaModal` — el mismo que aparece tras un cobro de mesero
#      (fix 1.3).

@require_POST
@sesion_cliente_requerida
def paypal_crear_orden_cliente(request):
    """
    POST JSON — crea una orden de pago en la API de PayPal (paso 1 del flujo redirect).

    Calcula el subtotal (individual o grupal), suma la propina opcional y solicita
    una orden CAPTURE a PayPal con return_url/cancel_url apuntando a vistas locales
    que retoman el flujo tras la aprobación. Devuelve `order_id` + `approve_url`
    para que el frontend redirija la pestaña actual.

    Body JSON:
        tipo    -- "individual" (solo esta sesión) o "grupal" (toda la mesa).
        propina -- monto decimal opcional (str o número). Default 0.

    Retorna JSON: {ok, order_id, approve_url, subtotal, propina, total}
    """
    import logging as _log
    import urllib.request as urlreq
    from apps.mesero.views import _paypal_base, _paypal_access_token, _paypal_cfg as cfg
    from django.db.models import Sum

    try:
        sesion = request.sesion_cliente

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}

        tipo = data.get("tipo", "individual")
        # 1.6: propina opcional ingresada por el cliente. La validamos como Decimal
        # no-negativo; cualquier basura se neutraliza a 0.
        try:
            propina = Decimal(str(data.get("propina", "0") or "0")).quantize(Decimal("0.01"))
            if propina < 0:
                propina = Decimal("0.00")
        except Exception:
            propina = Decimal("0.00")

        if tipo == "grupal":
            sesiones = sesion.mesa.sesiones.filter(estado="activa")
            subtotal = DetallePedido.objects.filter(
                pedido__sesion__in=sesiones
            ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")
        else:
            pedidos_sesion = sesion.pedidos.prefetch_related("detalles").exclude(estado="cancelado")
            subtotal = Decimal(str(sum(
                sum(d.subtotal_calculado for d in p.detalles.all()) for p in pedidos_sesion
            )))

        subtotal = subtotal.quantize(Decimal("0.01"))
        total    = (subtotal + propina).quantize(Decimal("0.01"))

        client_id = cfg("paypal_client_id")
        secret    = cfg("paypal_secret")
        modo      = cfg("paypal_modo", "sandbox")

        if not client_id or not secret:
            return JsonResponse({"ok": False, "error": "Pago en línea no disponible en este momento."}, status=503)

        # URLs absolutas que PayPal usará tras aprobar / cancelar. Se construyen con
        # request.build_absolute_uri para respetar el dominio actual (igual que
        # generate_qr_base64 en Mesa).
        return_url = request.build_absolute_uri(reverse("cliente:paypal_retorno"))
        cancel_url = request.build_absolute_uri(reverse("cliente:paypal_cancelar"))

        try:
            access_token = _paypal_access_token(client_id, secret, modo)
            # `breakdown`: declara explícitamente item_total + propina (PayPal lo
            # exige cuando el total no es solo item_total, para evitar VALIDATION_ERROR).
            breakdown = {
                "item_total": {"currency_code": "MXN", "value": str(subtotal)},
            }
            if propina > 0:
                breakdown["handling"] = {"currency_code": "MXN", "value": str(propina)}

            order_body = json.dumps({
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": "MXN",
                        "value": str(total),
                        "breakdown": breakdown,
                    },
                }],
                "application_context": {
                    "brand_name": "Mochi Matcha",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            }).encode()
            req = urlreq.Request(
                f"{_paypal_base(modo)}/v2/checkout/orders",
                data=order_body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            with urlreq.urlopen(req, timeout=15) as r:
                order = json.loads(r.read())
        except Exception as exc:
            return JsonResponse({"ok": False, "error": f"Error al contactar PayPal: {exc}"}, status=502)

        # Extraer el approve_url. PayPal usa rel="approve" en sandbox y rel="payer-action"
        # en algunas integraciones; aceptamos cualquiera.
        approve_url = next(
            (l["href"] for l in order.get("links", []) if l.get("rel") in ("approve", "payer-action")),
            None,
        )
        if not approve_url:
            return JsonResponse({"ok": False, "error": "PayPal no devolvió URL de aprobación."}, status=502)

        # Guardar contexto en la sesión Django para que paypal_retorno_cliente sepa
        # qué tipo de cobro hacer al volver (sin confiar en query params manipulables).
        request.session[f"paypal_order:{order['id']}"] = {
            "tipo": tipo,
            "propina": str(propina),
            "sesion_id": sesion.pk,
        }
        request.session.modified = True

        return JsonResponse({
            "ok": True,
            "order_id": order["id"],
            "approve_url": approve_url,
            "subtotal": float(subtotal),
            "propina": float(propina),
            "total": float(total),
        })
    except Exception as exc:
        _log.exception("PayPal crear orden error")
        return JsonResponse({
            "ok": False,
            "error": "Error interno al iniciar pago. Intenta más tarde.",
        }, status=500)


def _paypal_aplicar_captura(sesion, order_id, tipo, propina):
    """
    Helper compartido entre `paypal_capturar_cliente` (flujo JSON legacy) y
    `paypal_retorno_cliente` (flujo redirect, fix 1.7).

    Valida el estado, llama a PayPal /capture y actualiza SolicitudPago + sesión.
    Retorna (ticket_dict | None, error_msg | None, http_status).
    """
    import urllib.request as urlreq
    from django.db import transaction as db_transaction
    from apps.mesero.views import _paypal_base, _paypal_access_token, _paypal_cfg as cfg
    from apps.pedidos.models import SolicitudPago
    from apps.catalogs.models import MetodoPago, EstadoSolicitud
    from django.db.models import Sum

    # E5: validar el estado ANTES de capturar en PayPal. Capturar primero y
    # rechazar después cobraría dinero real sin aplicarlo a ninguna cuenta.
    if tipo == "grupal":
        if not sesion.mesa.sesiones.filter(estado="activa").exists():
            return None, "La cuenta de esta mesa ya fue saldada.", 409
    else:
        if sesion.estado != "activa":
            return None, "Tu cuenta ya fue saldada.", 409

    client_id = cfg("paypal_client_id")
    secret    = cfg("paypal_secret")
    modo      = cfg("paypal_modo", "sandbox")

    if not client_id or not secret:
        return None, "Pago en línea no disponible.", 503

    try:
        access_token = _paypal_access_token(client_id, secret, modo)
        req = urlreq.Request(
            f"{_paypal_base(modo)}/v2/checkout/orders/{order_id}/capture",
            data=b"{}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        with urlreq.urlopen(req, timeout=15) as r:
            capture = json.loads(r.read())
    except Exception as exc:
        return None, f"Error al capturar pago: {exc}", 502

    if capture.get("status") != "COMPLETED":
        return None, "El pago no fue completado en PayPal.", 402

    metodo_paypal       = MetodoPago.objects.filter(descripcion__iexact="paypal").first()
    estado_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")
    mesa = sesion.mesa
    total_consumo       = Decimal("0.00")
    sesiones_para_ticket = []

    propina = Decimal(str(propina or "0")).quantize(Decimal("0.01"))
    if propina < 0:
        propina = Decimal("0.00")

    with db_transaction.atomic():
        if tipo == "grupal":
            sesiones_locked = list(
                mesa.sesiones.select_for_update(nowait=False).filter(estado="activa")
            )
            if not sesiones_locked:
                return None, "La cuenta de esta mesa ya fue saldada.", 409
            sesiones_para_ticket = sesiones_locked
            total_consumo = DetallePedido.objects.filter(
                pedido__sesion__in=sesiones_locked
            ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

            sol = None
            for s in sesiones_locked:
                existing = SolicitudPago.objects.filter(sesion=s, estado_solicitud=estado_pendiente).first()
                if existing:
                    existing.estado_solicitud   = estado_procesada
                    existing.metodo_pago        = metodo_paypal
                    existing.referencia_externa = order_id
                    existing.detalle_pago       = "PAYPAL"
                    existing.propina_sugerida   = propina
                    existing.save(update_fields=[
                        "estado_solicitud", "metodo_pago", "referencia_externa",
                        "detalle_pago", "propina_sugerida",
                    ])
                    if sol is None:
                        sol = existing
                s.estado = "pagada"
                s.save(update_fields=["estado"])

            if sol is None:
                sol = SolicitudPago.objects.create(
                    mesa=mesa, tipo="grupal", total_mesa=total_consumo,
                    propina_sugerida=propina,
                    estado_solicitud=estado_procesada,
                    metodo_pago=metodo_paypal, referencia_externa=order_id, detalle_pago="PAYPAL",
                )
            sol.sesiones_cubiertas.set(sesiones_locked)

            from apps.mesero.views import _post_pago_mesa
            _post_pago_mesa(mesa, user=None)
        else:
            sesion_locked = (
                SesionCliente.objects.select_for_update(nowait=False)
                .filter(pk=sesion.pk, estado="activa").first()
            )
            if sesion_locked is None:
                return None, "Esta sesión ya fue procesada.", 409

            sesiones_para_ticket = [sesion_locked]
            total_consumo = DetallePedido.objects.filter(
                pedido__sesion=sesion_locked
            ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

            sol, _created = SolicitudPago.objects.get_or_create(
                sesion=sesion_locked, estado_solicitud=estado_pendiente,
                defaults={
                    "tipo": "individual",
                    "total_individual": total_consumo,
                    "mesa": mesa,
                    "propina_sugerida": propina,
                },
            )
            sol.estado_solicitud   = estado_procesada
            sol.metodo_pago        = metodo_paypal
            sol.referencia_externa = order_id
            sol.detalle_pago       = "PAYPAL"
            sol.propina_sugerida   = propina
            sol.save(update_fields=[
                "estado_solicitud", "metodo_pago", "referencia_externa",
                "detalle_pago", "propina_sugerida",
            ])

            sesion_locked.estado = "pagada"
            sesion_locked.save(update_fields=["estado"])
            sol.sesiones_cubiertas.set([sesion_locked])

            from apps.mesero.views import _post_pago_mesa
            _post_pago_mesa(mesa, user=None)

    total_pagado = (total_consumo + propina).quantize(Decimal("0.01"))

    items_ticket = []
    for s_ref in sesiones_para_ticket:
        for p in s_ref.pedidos.prefetch_related("detalles__producto").exclude(estado="cancelado"):
            for d in p.detalles.all():
                items_ticket.append({
                    "nombre": d.producto.nombre,
                    "cantidad": d.cantidad,
                    "subtotal": float(d.subtotal_calculado),
                })

    from apps.mesas.models import AlertaMesero
    propina_txt = f" + propina ${float(propina):.2f}" if propina > 0 else ""
    AlertaMesero.objects.create(
        mesa=mesa,
        sesion=sesion,
        tipo="cuenta",
        mensaje=(
            f"{'Toda la mesa' if tipo == 'grupal' else sesion.alias} pagó por PayPal"
            f" — ${float(total_pagado):.2f}{propina_txt}"
        ),
    )

    subtotal_sesion = DetallePedido.objects.filter(
        pedido__sesion=sesion
    ).exclude(pedido__estado="cancelado").aggregate(
        t=Sum("subtotal_calculado"),
    )["t"] or Decimal("0.00")

    ticket = {
        "alias": sesion.alias,
        "mesa": str(mesa.numero_mesa),
        "tipo": tipo,
        "metodo": "PayPal",
        "items": items_ticket,
        "subtotal_sesion": float(subtotal_sesion),
        "subtotal_total": float(total_consumo),
        "propina": float(propina),
        "total_pagado": float(total_pagado),
        "referencia": order_id,
        # 1.8: sol_id permite al cliente abrir el mismo ticket PDF que el mesero,
        # garantizando layout consistente entre ambas vistas.
        "sol_id": sol.pk if sol else None,
    }
    return ticket, None, 200


@require_POST
@sesion_cliente_requerida
def paypal_capturar_cliente(request):
    """
    POST JSON — captura la orden aprobada por el cliente (flujo legacy JSON).

    Conservado para retrocompatibilidad del SDK Buttons. El flujo actual de la
    UI es redirect (paypal_retorno_cliente), pero esta vista sigue funcionando
    para clientes/tests que envíen order_id por JSON.

    Body JSON:
        order_id -- identificador de la orden PayPal aprobada por el cliente.
        tipo     -- "individual" o "grupal".
        propina  -- decimal opcional.

    Retorna JSON: {ok, mensaje, ticket}
    """
    import logging as _log

    try:
        sesion = request.sesion_cliente

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

        order_id = data.get("order_id", "").strip()
        tipo     = data.get("tipo", "individual")
        propina  = data.get("propina", "0")

        if not order_id:
            return JsonResponse({"ok": False, "error": "order_id requerido"}, status=400)

        ticket, err, status = _paypal_aplicar_captura(sesion, order_id, tipo, propina)
        if err:
            return JsonResponse({"ok": False, "error": err}, status=status)

        return JsonResponse({
            "ok": True,
            "mensaje": "¡Pago completado con éxito!",
            "ticket": ticket,
        })
    except Exception as exc:
        _log.exception("PayPal capturar orden error")
        return JsonResponse({
            "ok": False,
            "error": "Error interno al procesar el pago. Intenta más tarde.",
        }, status=500)


@sesion_cliente_requerida
def paypal_retorno_cliente(request):
    """
    GET — endpoint al que PayPal redirige tras la aprobación (fix 1.7).

    PayPal añade `?token=<order_id>&PayerID=...`. Recuperamos el contexto guardado
    en la sesión Django (tipo + propina), capturamos la orden y dejamos el ticket
    listo para que pedidos.html lo muestre en el modal unificado.

    En éxito redirige a /cliente/pedidos/?paypal_ok=1.
    En error redirige a /cliente/pedidos/?paypal_error=1 con un mensaje en sesión.
    """
    order_id = request.GET.get("token", "").strip()
    if not order_id:
        request.session["paypal_error_msg"] = "PayPal no devolvió la orden a procesar."
        request.session.modified = True
        return redirect(reverse("cliente:pedidos") + "?paypal_error=1")

    ctx_key = f"paypal_order:{order_id}"
    ctx = request.session.get(ctx_key)
    if not ctx:
        # Sin contexto previo no podemos confiar en tipo/propina; abortamos.
        request.session["paypal_error_msg"] = "No se encontró el contexto del pago. Inténtalo de nuevo."
        request.session.modified = True
        return redirect(reverse("cliente:pedidos") + "?paypal_error=1")

    tipo    = ctx.get("tipo", "individual")
    propina = ctx.get("propina", "0")

    sesion = request.sesion_cliente

    ticket, err, _status = _paypal_aplicar_captura(sesion, order_id, tipo, propina)

    # Limpiar contexto consumido (one-shot).
    request.session.pop(ctx_key, None)

    if err:
        request.session["paypal_error_msg"] = err
        request.session.modified = True
        return redirect(reverse("cliente:pedidos") + "?paypal_error=1")

    request.session["paypal_ticket_inicial"] = ticket
    request.session.modified = True
    return redirect(reverse("cliente:pedidos") + "?paypal_ok=1")


@sesion_cliente_requerida
def paypal_cancelar_cliente(request):
    """
    GET — endpoint al que PayPal redirige si el cliente cancela en su pasarela.

    Limpia el contexto de la orden (si existe) y vuelve a /cliente/pedidos/
    indicando cancelación al template para que muestre un toast amable.
    """
    order_id = request.GET.get("token", "").strip()
    if order_id:
        request.session.pop(f"paypal_order:{order_id}", None)
        request.session.modified = True
    return redirect(reverse("cliente:pedidos") + "?paypal_cancelado=1")


# ─── Ticket PDF (cliente) ────────────────────────────────────────────────────
#
# 1.8: el cliente y el mesero ven el MISMO ticket con el MISMO layout, generado
# desde la misma plantilla `mesero/ticket.html` vía WeasyPrint. La diferencia
# es solo la autorización: el cliente solo puede ver tickets de pagos que
# cubrieron su mesa actual (sol.mesa == sesion.mesa).

@sesion_cliente_requerida
def ticket_pdf_cliente(request, solicitud_id):
    """
    GET — descarga el PDF del ticket de la cuenta del cliente.

    Reutiliza `_ticket_context` y la plantilla `mesero/ticket.html` para que el
    cliente vea exactamente el mismo formato que imprime el mesero (fix 1.8).
    Solo se permite ver tickets cuya mesa coincide con la sesión del cliente.
    """
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from apps.pedidos.models import SolicitudPago
    from apps.mesero.views import _ticket_context

    sesion = request.sesion_cliente
    sol = get_object_or_404(SolicitudPago, pk=solicitud_id)

    # Autorización: el ticket debe corresponder a la mesa de la sesión actual.
    if sol.mesa_id != sesion.mesa_id:
        return JsonResponse({"ok": False, "error": "No autorizado."}, status=403)

    # `_ticket_context` espera el "user" del mesero — en este flujo no hay user
    # autenticado por accounts, así que pasamos None y la plantilla muestra el
    # mesero registrado en la SolicitudPago si lo hay.
    html_str = render_to_string(
        "mesero/ticket.html", _ticket_context(sol, None), request=request,
    )
    try:
        import weasyprint
    except ImportError:
        return HttpResponse(html_str)

    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="ticket-{sol.pk:06d}.pdf"'
    return resp


# ─── Calcular descuentos del carrito (informativo, no autoritativo) ───────────

@require_POST
def calcular_carrito(request):
    """
    POST JSON {items: [{producto_id, cantidad, subtotal, modificadores, notas}]}
    Devuelve estimación de descuentos con promociones activas.
    El backend es la fuente de verdad al confirmar; esto es solo informativo.
    """
    sesion = request.session.get("sesion_id")
    sesion_obj = None
    if sesion:
        from apps.mesas.models import SesionCliente as SC
        sesion_obj = SC.objects.filter(pk=sesion, estado="activa").first()

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    items = data.get("items", [])
    if not items:
        return JsonResponse({"ok": True, "subtotal": 0, "descuento": 0, "total": 0, "promociones": []})

    from apps.pedidos.utils import aplicar_promociones
    from decimal import Decimal

    items_calc = []
    for item in items:
        items_calc.append({
            "producto_id": item.get("producto_id"),
            "cantidad": item.get("cantidad", 1),
            "subtotal": float(item.get("subtotal", 0)),
            "modificadores": item.get("modificadores", []),
            "notas": item.get("notas", ""),
        })

    promo_seleccionada = data.get("promocion_id")

    subtotal_original = sum(Decimal(str(i["subtotal"])) for i in items_calc)
    items_con_promo, promos, elegibles = aplicar_promociones(
        items_calc, sesion_obj, promocion_id=promo_seleccionada
    )
    total_con_promo = sum(Decimal(str(i["subtotal"])) for i in items_con_promo)
    descuento = subtotal_original - total_con_promo

    # Mapa producto_id → precio con descuento para mostrar en UI
    precios_map = {i["producto_id"]: float(Decimal(str(i["subtotal"]))) for i in items_con_promo}

    def _serializa(p):
        return {
            "id": p.pk,
            "titulo": p.titulo,
            "descripcion": (
                p.descripcion_corta
                or (p.tipo_descuento.descripcion if p.tipo_descuento else "")
            ),
        }

    return JsonResponse({
        "ok": True,
        "subtotal": float(subtotal_original),
        "descuento": float(descuento),
        "total": float(total_con_promo),
        "promociones": [_serializa(p) for p in promos],
        # Todas las promos elegibles para que el cliente pueda elegir si hay >1
        "promociones_elegibles": [_serializa(p) for p in elegibles],
        "promocion_seleccionada": promos[0].pk if promos else None,
        # Si hay varias y el cliente aún no eligió, el frontend debe pedir selección
        "requiere_seleccion": len(elegibles) > 1 and not promos,
        "precios_map": precios_map,
    })


# ─── Estado de la sesión (polling) + cierre voluntario ────────────────────────

@require_GET
@sesion_cliente_requerida
def estado_sesion(request):
    """
    Endpoint de polling para que el cliente detecte cuándo su cuenta fue
    pagada (problema 2). Devuelve:
      - estado: "activa" | "pagada"
      - pagada: bool
      - ticket: desglose de lo consumido por ESTA sesión cuando ya fue pagada,
        más metadatos del pago (método, total, tipo, propina). Para un pago
        grupal, cada cliente recibe en su pantalla el ticket de su propio
        consumo; para individual, solo el cliente que pagó.
    """
    from apps.pedidos.models import SolicitudPago

    sesion = request.sesion_cliente
    pagada = (sesion.estado == "pagada")

    payload = {
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "estado": sesion.estado,
        "pagada": pagada,
    }

    if not pagada:
        return JsonResponse(payload)

    # Items consumidos por ESTA sesión (no se pierde ningún producto: se leen
    # todos los DetallePedido de pedidos no cancelados de la sesión).
    items = []
    total_sesion = Decimal("0.00")
    for p in sesion.pedidos.prefetch_related("detalles__producto").exclude(estado="cancelado"):
        for d in p.detalles.all():
            items.append({
                "nombre": d.producto.nombre,
                "cantidad": d.cantidad,
                "subtotal": float(d.subtotal_calculado),
            })
            total_sesion += d.subtotal_calculado

    # Buscar la SolicitudPago que saldó esta sesión: la individual ligada a la
    # sesión, o la grupal de la mesa. Ambas en estado "procesada".
    sol = (
        SolicitudPago.objects
        .filter(sesion=sesion, estado_solicitud__descripcion="procesada")
        .select_related("metodo_pago")
        .order_by("-fecha_hora")
        .first()
    )
    if sol is None:
        sol = (
            SolicitudPago.objects
            .filter(mesa=sesion.mesa, tipo="grupal", estado_solicitud__descripcion="procesada")
            .select_related("metodo_pago")
            .order_by("-fecha_hora")
            .first()
        )

    metodo = ""
    tipo_pago = "individual"
    total_pagado = float(total_sesion)
    if sol:
        metodo = (sol.metodo_pago.descripcion if sol.metodo_pago else sol.detalle_pago) or ""
        tipo_pago = sol.tipo
        # En grupal, total_mesa es el total cobrado; en individual, lo de la sesión.
        if sol.tipo == "grupal" and sol.total_mesa is not None:
            total_pagado = float(sol.total_mesa)
        elif sol.total_individual is not None:
            total_pagado = float(sol.total_individual)

    payload["ticket"] = {
        "alias": sesion.alias,
        "mesa": str(sesion.mesa.numero_mesa),
        "tipo": tipo_pago,
        "metodo": metodo,
        "items": items,
        "subtotal_sesion": float(total_sesion),
        "total_pagado": total_pagado,
        # 1.8: sol_id para abrir el mismo PDF que ve el mesero.
        "sol_id": sol.pk if sol else None,
    }
    return JsonResponse(payload)


@require_POST
@sesion_cliente_requerida
def cerrar_sesion_cliente(request):
    """
    Cierre voluntario de la sesión por el cliente (botón "Salir" de la pantalla
    de cuenta pagada). Pasa la sesión a "cerrada" y borra la cookie. Solo se
    permite si la sesión ya fue pagada — una sesión activa no se cierra así.
    """
    sesion = request.sesion_cliente
    if sesion.estado == "activa":
        return JsonResponse({
            "ok": False,
            "error": "No puedes cerrar una sesión con cuenta abierta.",
        }, status=409)

    if sesion.estado != "cerrada":
        sesion.estado = "cerrada"
        sesion.save(update_fields=["estado"])

    response = JsonResponse({"ok": True, "redirect": "/bienvenida/"})
    from apps.cliente.middleware import CLIENT_COOKIE_NAME
    response.delete_cookie(CLIENT_COOKIE_NAME)
    return response


@require_GET
@sesion_cliente_requerida
def desglose_pago(request):
    """GET /pago/desglose/?tipo=individual|grupal&propina_pct=0
    Solo lectura — devuelve items + totales para previsualizar antes del pago.
    """
    sesion = request.sesion_cliente
    tipo = request.GET.get("tipo", "individual")
    try:
        propina_pct = max(0, int(request.GET.get("propina_pct", 0) or 0))
    except (ValueError, TypeError):
        propina_pct = 0

    base_qs = (
        DetallePedido.objects
        .exclude(pedido__estado="cancelado")
        .select_related("producto", "promocion")
        .prefetch_related("modificadores")
    )
    if tipo == "grupal":
        sesiones = sesion.mesa.sesiones.filter(estado="activa")
        detalles_qs = base_qs.filter(pedido__sesion__in=sesiones)
    else:
        detalles_qs = base_qs.filter(pedido__sesion=sesion)

    items = []
    subtotal_neto = Decimal("0.00")
    subtotal_bruto = Decimal("0.00")

    for d in detalles_qs:
        extras = sum(m.precio_extra_aplicado for m in d.modificadores.all())
        bruto_item = (d.producto.precio + extras) * d.cantidad
        items.append({
            "nombre": d.producto.nombre,
            "cantidad": d.cantidad,
            "subtotal_bruto": float(bruto_item),
            "subtotal": float(d.subtotal_calculado),
            "promo_aplicada": d.promocion.titulo if d.promocion else None,
        })
        subtotal_neto += d.subtotal_calculado
        subtotal_bruto += bruto_item

    descuentos = max(Decimal("0.00"), subtotal_bruto - subtotal_neto)
    propina = (subtotal_neto * Decimal(propina_pct) / Decimal(100)).quantize(Decimal("0.01"))
    total = (subtotal_neto + propina).quantize(Decimal("0.01"))

    return JsonResponse({
        "ok": True,
        "items": items,
        "subtotal_bruto": float(subtotal_bruto),
        "descuentos": float(descuentos),
        "subtotal_neto": float(subtotal_neto),
        "propina": float(propina),
        "propina_sugerida": float((subtotal_neto * Decimal("0.10")).quantize(Decimal("0.01"))),
        "total": float(total),
    })
