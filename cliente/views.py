"""
cliente/views.py — Vistas para el módulo de cliente (sin autenticación Django).
"""
import json
import uuid
import random
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from accounts.decorators import sesion_cliente_requerida
from mesas.models import Mesa, SesionCliente
from menu.models import Categoria, Producto, Promocion
from pedidos.models import Pedido, DetallePedido, DetalleModificador
from catalogs.models import ModalidadIngreso


def _get_carrito(request):
    return request.session.get("carrito", [])

def _save_carrito(request, carrito):
    request.session["carrito"] = carrito
    request.session.modified = True

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
        "pin": mesa.pin_actual,
        "sesiones_activas": list(sesiones),
        "count": len(sesiones),
    })


# ─── Bienvenida ───────────────────────────────────────────────────────────────

def bienvenida(request):
    mesa_id = request.GET.get("mesa") or request.session.get("mesa_id")
    if not mesa_id:
        return render(request, "cliente/bienvenida.html", {"error_mesa": True})
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    step = request.GET.get("step", "")
    sesiones_activas = mesa.sesiones.filter(estado="activa").count()
    return render(request, "cliente/bienvenida.html", {
        "mesa": mesa, "step": step, "sesiones_activas": sesiones_activas,
    })


@require_POST
def crear_sesion(request, mesa_id):
    """POST — crea SesionCliente, genera PIN si es la primera sesión."""
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    alias = request.POST.get("alias", "").strip()[:50]
    modalidad_str = request.POST.get("modalidad", "qr")

    if not alias:
        return redirect(f"/bienvenida/?mesa={mesa_id}")

    if SesionCliente.objects.filter(mesa=mesa, alias=alias, estado="activa").exists():
        return render(request, "cliente/bienvenida.html", {
            "mesa": mesa, "step": "nuevo",
            "sesiones_activas": mesa.sesiones.filter(estado="activa").count(),
            "error": "Ese alias ya está en uso en esta mesa. Elige otro.",
        })

    modalidad, _ = ModalidadIngreso.objects.get_or_create(descripcion=modalidad_str)
    token = uuid.uuid4().hex

    # Generar PIN si la mesa no tiene uno (primera sesión)
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
    from django.utils import timezone
    categorias = list(Categoria.objects.prefetch_related(
        "productos__grupos_modificadores__opciones"
    ).all())
    for cat in categorias:
        cat.productos_disponibles = [p for p in cat.productos.all() if p.disponible]

    # Promoción activa destacada (para banner)
    ahora = timezone.now()
    promo_banner = Promocion.objects.filter(activa=True, fecha_inicio__lte=ahora, fecha_fin__gte=ahora).first()

    carrito = _get_carrito(request)
    sesion = request.sesion_cliente
    return render(request, "cliente/menu.html", {
        "categorias": categorias,
        "carrito_count": len(carrito),
        "sesion": sesion,
        "mesa": sesion.mesa,
        "pin_mesa": sesion.mesa.pin_actual,
        "promo_banner": promo_banner,
    })


# ─── Carrito ──────────────────────────────────────────────────────────────────

@sesion_cliente_requerida
def carrito(request):
    items = _get_carrito(request)
    total = sum(item.get("subtotal", 0) for item in items)
    sesion = request.sesion_cliente
    return render(request, "cliente/carrito.html", {
        "carrito": items, "total": total,
        "carrito_count": len(items), "sesion": sesion,
        "mesa": sesion.mesa, "pin_mesa": sesion.mesa.pin_actual,
    })


@require_POST
@sesion_cliente_requerida
def agregar_carrito(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    producto_id = data.get("producto_id")
    cantidad = int(data.get("cantidad", 1))
    modificadores_ids = data.get("modificadores", [])
    notas = data.get("notas", "")
    producto = get_object_or_404(Producto, pk=producto_id, disponible=True)
    from menu.models import OpcionModificador
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
    _save_carrito(request, [])
    return JsonResponse({"ok": True})


@require_POST
@sesion_cliente_requerida
def confirmar_pedido(request):
    items = _get_carrito(request)
    if not items:
        return JsonResponse({"ok": False, "error": "El carrito está vacío"}, status=400)
    sesion = request.sesion_cliente
    from menu.models import OpcionModificador
    pedido = Pedido.objects.create(sesion=sesion, modalidad=sesion.modalidad_ingreso)
    for item in items:
        producto = get_object_or_404(Producto, pk=item["producto_id"])
        detalle = DetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=item["cantidad"],
            notas=item.get("notas", ""), subtotal_calculado=item["subtotal"],
        )
        for op_data in item.get("modificadores", []):
            try:
                opcion = OpcionModificador.objects.get(pk=op_data["id"])
                DetalleModificador.objects.create(
                    detalle=detalle, opcion=opcion,
                    precio_extra_aplicado=op_data["extra"],
                )
            except OpcionModificador.DoesNotExist:
                pass
    _save_carrito(request, [])
    return JsonResponse({"ok": True, "pedido_id": pedido.pk})


# ─── Pedidos ──────────────────────────────────────────────────────────────────

@sesion_cliente_requerida
def pedidos(request):
    sesion = request.sesion_cliente
    mis_pedidos = sesion.pedidos.prefetch_related(
        "detalles__producto", "detalles__modificadores__opcion"
    ).order_by("-fecha_hora_ingreso")
    total_general = sum(
        sum(d.subtotal_calculado for d in p.detalles.all()) for p in mis_pedidos
    )
    return render(request, "cliente/pedidos.html", {
        "pedidos": mis_pedidos, "total_general": total_general,
        "carrito_count": len(_get_carrito(request)),
        "sesion": sesion, "mesa": sesion.mesa, "pin_mesa": sesion.mesa.pin_actual,
    })


@require_GET
@sesion_cliente_requerida
def estado_pedidos(request):
    sesion = request.sesion_cliente
    data = []
    for p in sesion.pedidos.prefetch_related("detalles__producto").order_by("-fecha_hora_ingreso"):
        data.append({
            "id": p.pk, "estado": p.estado,
            "estado_display": p.get_estado_display(),
            "fecha": p.fecha_hora_ingreso.strftime("%H:%M"),
            "items": [{"nombre": d.producto.nombre, "cantidad": d.cantidad} for d in p.detalles.all()],
        })
    return JsonResponse({"ok": True, "pedidos": data})


@require_POST
@sesion_cliente_requerida
def solicitar_ayuda(request):
    return JsonResponse({"ok": True, "mensaje": "Se ha notificado a tu mesero."})


@require_POST
@sesion_cliente_requerida
def solicitar_cuenta(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}
    sesion = request.sesion_cliente
    tipo = data.get("tipo", "individual")
    from pedidos.models import SolicitudPago
    from catalogs.models import EstadoSolicitud
    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")
    SolicitudPago.objects.create(
        tipo=tipo, sesion=sesion, mesa=sesion.mesa, estado_solicitud=estado_pendiente,
    )
    return JsonResponse({"ok": True, "mensaje": "Tu mesero se acercará en breve."})
