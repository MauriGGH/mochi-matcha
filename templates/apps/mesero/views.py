"""
mesero/views.py — Con pedido asistido POST completo.
"""
import json
import uuid
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET

from apps.accounts.decorators import mesero_requerido
from apps.mesas.models import Mesa, SesionCliente
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador, SolicitudPago
from apps.catalogs.models import MetodoPago, EstadoSolicitud, ModalidadIngreso
from apps.menu.models import Producto  # asegúrate de importar al inicio


# ─── Auth ─────────────────────────────────────────────────────────────────────

def login_mesero(request):
    if request.user.is_authenticated and request.user.rol in ("mesero", "gerente", "admin"):
        return redirect("mesero:mapa_mesas")
    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, username=usuario, password=contrasena)
        if user and user.rol in ("mesero", "gerente", "admin") and user.is_active:
            login(request, user)
            return redirect("mesero:mapa_mesas")
        error = "Credenciales incorrectas o sin acceso a este módulo."
    return render(request, "base/login.html", {
        "rol": "mesero", "rol_display": "Mesero",
        "form_action": "/mesero/login/", "error": error,
        "usuario_previo": request.POST.get("usuario", ""),
    })


def logout_mesero(request):
    logout(request)
    return redirect("mesero:login_mesero")


# ─── Mapa de mesas ────────────────────────────────────────────────────────────

@mesero_requerido
def mapa_mesas(request):
    from apps.menu.models import Categoria
    mesas = Mesa.objects.prefetch_related("sesiones").order_by("numero_mesa")
    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    categorias = Categoria.objects.prefetch_related(
        "productos__grupos_modificadores__opciones"
    ).filter(productos__disponible=True).distinct()
    return render(request, "mesero/mapa_mesas.html", {
        "mesas": mesas,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
        "categorias": categorias,
    })


@require_GET
@mesero_requerido
def mesas_estado(request):
    mesas = Mesa.objects.prefetch_related("sesiones__pedidos").order_by("numero_mesa")
    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    data = []
    for m in mesas:
        sesiones_activas = m.sesiones.filter(estado="activa")
        pedidos_en_cocina = 0
        pedidos_listos = 0
        tiene_solicitud = False

        for s in sesiones_activas:
            pedidos_en_cocina += s.pedidos.filter(estado__in=["recibido", "preparando"]).count()
            pedidos_listos += s.pedidos.filter(estado="listo").count()
            if s.solicitudes_pago.filter(estado_solicitud__descripcion="pendiente").exists():
                tiene_solicitud = True

        # Estado visual de la mesa
        if m.estado == "libre":
            estado_visual = "libre"
        elif tiene_solicitud:
            estado_visual = "cobrando"
        elif pedidos_listos > 0:
            estado_visual = "listo"
        elif pedidos_en_cocina > 0:
            estado_visual = "cocina"
        else:
            estado_visual = "ocupada"

        data.append({
            "id": m.pk,
            "numero": m.numero_mesa,
            "estado": m.estado,
            "estado_visual": estado_visual,
            "ubicacion": m.ubicacion or "",
            "capacidad": m.capacidad,
            "pin": m.pin_actual or "",
            "clientes": sesiones_activas.count(),
            "pedidos_cocina": pedidos_en_cocina,
            "pedidos_listos": pedidos_listos,
            "tiene_solicitud": tiene_solicitud,
        })
    return JsonResponse({
        "ok": True,
        "mesas": data,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
    })


@require_GET
@mesero_requerido
def detalle_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    sesiones = mesa.sesiones.filter(estado="activa").order_by("fecha_inicio")

    sesiones_data = []
    for s in sesiones:
        pedidos_sesion = s.pedidos.prefetch_related(
            "detalles__producto", "detalles__modificadores__opcion"
        ).order_by("-fecha_hora_ingreso")
        total_sesion = sum(
            sum(d.subtotal_calculado for d in p.detalles.all()) for p in pedidos_sesion
        )
        sesiones_data.append({
            "id": s.pk,
            "alias": s.alias,
            "total": float(total_sesion),
            "pedidos": [
                {
                    "id": p.pk,
                    "estado": p.estado,
                    "estado_display": p.get_estado_display(),
                    "fecha": p.fecha_hora_ingreso.strftime("%H:%M"),
                    "items": [
                        {
                            "nombre": d.producto.nombre,
                            "cantidad": d.cantidad,
                            "subtotal": float(d.subtotal_calculado),
                            "notas": d.notas or "",
                            "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
                        }
                        for d in p.detalles.all()
                    ],
                }
                for p in pedidos_sesion
            ],
        })

    # Solicitudes pendientes
    solicitudes = []
    for s in sesiones:
        for sol in s.solicitudes_pago.filter(estado_solicitud__descripcion="pendiente").order_by("-fecha_hora"):
            solicitudes.append({
                "id": sol.pk,
                "alias": s.alias,
                "tipo": sol.tipo,
                "tipo_display": sol.get_tipo_display(),
                "total": float(sol.total_mesa or sol.total_individual or 0),
                "fecha": sol.fecha_hora.strftime("%H:%M"),
            })

    # Total general de la mesa
    total_mesa = sum(s["total"] for s in sesiones_data)

    return JsonResponse({
        "ok": True,
        "mesa_libre": mesa.estado == "libre",
        "mesa_id": mesa.pk,
        "numero_mesa": mesa.numero_mesa,
        "pin": mesa.pin_actual or "",
        "estado": mesa.estado,
        "sesiones": sesiones_data,
        "solicitudes": solicitudes,
        "total_mesa": total_mesa,
    })


# ─── Pedidos ──────────────────────────────────────────────────────────────────

@mesero_requerido
def pedidos_listos(request):
    pedidos = Pedido.objects.filter(estado="listo").select_related(
        "sesion__mesa"
    ).prefetch_related("detalles__producto").order_by("fecha_hora_ingreso")
    return render(request, "mesero/mapa_mesas.html", {
        "pedidos_listos": pedidos, "vista": "listos",
        "listos_count": pedidos.count(),
    })


@require_POST
@mesero_requerido
def entregar_pedido(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)
    pedido = get_object_or_404(Pedido, pk=data.get("pedido_id"))
    pedido.estado = "entregado"
    pedido.empleado_entrega = request.user
    from django.utils import timezone
    pedido.fecha_hora_entrega = timezone.now()
    pedido.save(update_fields=["estado", "empleado_entrega", "fecha_hora_entrega"])
    return JsonResponse({"ok": True})


@require_POST
@mesero_requerido
def cerrar_sesion(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)
    sesion = get_object_or_404(SesionCliente, pk=data.get("sesion_id"), estado="activa")
    sesion.estado = "cerrada"
    sesion.save(update_fields=["estado"])
    mesa = sesion.mesa
    if not mesa.sesiones.filter(estado="activa").exists():
        mesa.estado = "libre"
        mesa.pin_actual = None
        mesa.save(update_fields=["estado", "pin_actual"])
    return JsonResponse({"ok": True})


@require_POST
@mesero_requerido
def cerrar_mesa(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)
    mesa = get_object_or_404(Mesa, pk=data.get("mesa_id"))
    mesa.sesiones.filter(estado="activa").update(estado="cerrada")
    mesa.estado = "libre"
    mesa.pin_actual = None
    mesa.save(update_fields=["estado", "pin_actual"])
    return JsonResponse({"ok": True})


# ─── Pedido asistido ──────────────────────────────────────────────────────────

@mesero_requerido
def pedido_asistido(request):
    """GET — renderiza la vista del mapa con el modal de pedido asistido."""
    mesa_id = request.GET.get("mesa")
    mesas = Mesa.objects.filter(estado="ocupada").order_by("numero_mesa")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None
    from apps.menu.models import Categoria
    categorias = Categoria.objects.prefetch_related(
        "productos__grupos_modificadores__opciones"
    ).filter(productos__disponible=True).distinct()
    listos_count = Pedido.objects.filter(estado="listo").count()
    return render(request, "mesero/mapa_mesas.html", {
        "vista": "asistido", "mesa": mesa, "mesas": mesas,
        "categorias": categorias, "listos_count": listos_count,
    })


@require_POST
@mesero_requerido
def confirmar_pedido_asistido(request):
    """
    POST — crea un pedido asistido a nombre de una sesión específica.
    Body JSON: { sesion_id, items: [{producto_id, cantidad, modificadores, notas}] }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    sesion_id = data.get("sesion_id")
    items = data.get("items", [])

    if not sesion_id or not items:
        return JsonResponse({"ok": False, "error": "Datos incompletos"}, status=400)

    sesion = get_object_or_404(SesionCliente, pk=sesion_id, estado="activa")
    modalidad_asistido, _ = ModalidadIngreso.objects.get_or_create(descripcion="asistido")

    from apps.menu.models import Producto, OpcionModificador
    pedido = Pedido.objects.create(
        sesion=sesion,
        modalidad=modalidad_asistido,
        empleado_entrega=request.user,
    )

    for item in items:
        producto = get_object_or_404(Producto, pk=item.get("producto_id"), disponible=True)
        cantidad = int(item.get("cantidad", 1))
        modificadores_ids = item.get("modificadores", [])
        notas = item.get("notas", "")

        precio_extra = 0
        if modificadores_ids:
            for op in OpcionModificador.objects.filter(pk__in=modificadores_ids):
                precio_extra += float(op.precio_extra)

        subtotal = (float(producto.precio) + precio_extra) * cantidad
        detalle = DetallePedido.objects.create(
            pedido=pedido, producto=producto, cantidad=cantidad,
            notas=notas, subtotal_calculado=subtotal,
        )

        for op_id in modificadores_ids:
            try:
                opcion = OpcionModificador.objects.get(pk=op_id)
                DetalleModificador.objects.create(
                    detalle=detalle, opcion=opcion,
                    precio_extra_aplicado=float(opcion.precio_extra),
                )
            except OpcionModificador.DoesNotExist:
                pass

    return JsonResponse({"ok": True, "pedido_id": pedido.pk})


# ─── Alertas / solicitudes ────────────────────────────────────────────────────

@mesero_requerido
def alertas(request):
    solicitudes = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).select_related("mesa", "sesion").order_by("-fecha_hora")
    listos_count = Pedido.objects.filter(estado="listo").count()
    return render(request, "mesero/mapa_mesas.html", {
        "solicitudes": solicitudes, "vista": "alertas",
        "listos_count": listos_count,
    })


@mesero_requerido
def cuentas(request):
    return alertas(request)


# ─── Pago ─────────────────────────────────────────────────────────────────────

@mesero_requerido
def pago(request):
    mesa_id = request.GET.get("mesa")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None
    sesiones = mesa.sesiones.filter(estado="activa") if mesa else []
    metodos = MetodoPago.objects.all()
    total = 0
    pedidos_mesa = []
    if mesa:
        for s in sesiones:
            for p in s.pedidos.prefetch_related("detalles__producto").exclude(estado="cancelado"):
                pedidos_mesa.append(p)
                total += sum(d.subtotal_calculado for d in p.detalles.all())

    return render(request, "mesero/pago.html", {
        "mesa": mesa, "sesiones": sesiones,
        "pedidos": pedidos_mesa, "total": total, "metodos": metodos,
    })


@require_POST
@mesero_requerido
def procesar_pago(request):
    mesa_id = request.POST.get("mesa_id")
    metodo_id = request.POST.get("metodo_pago_id")
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    sesiones = mesa.sesiones.filter(estado="activa")
    if not sesiones.exists():
        return redirect("mesero:mapa_mesas")

    metodo = get_object_or_404(MetodoPago, pk=metodo_id) if metodo_id else None
    estado_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")

    for s in sesiones:
        SolicitudPago.objects.filter(
            sesion=s, estado_solicitud__descripcion="pendiente"
        ).update(estado_solicitud=estado_procesada, metodo_pago=metodo)
        s.estado = "pagada"
        s.save(update_fields=["estado"])

    mesa.estado = "libre"
    mesa.pin_actual = None
    mesa.save(update_fields=["estado", "pin_actual"])
    return redirect("mesero:mapa_mesas")

@require_GET
@mesero_requerido
def productos_json(request):
    """Devuelve lista de productos disponibles para pedido asistido."""
    productos = Producto.objects.filter(disponible=True).only('id', 'nombre', 'precio')
    data = [{"id": p.id, "nombre": p.nombre, "precio": float(p.precio)} for p in productos]
    return JsonResponse({"ok": True, "productos": data})


@require_POST
@mesero_requerido
def cancelar_pedido(request):
    """POST JSON: { pedido_id, motivo } — mesero cancela con motivo obligatorio."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    from apps.auditoria.models import Auditoria
    from django.db import transaction
    pedido_id = data.get("pedido_id")
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return JsonResponse({"ok": False, "error": "El motivo es obligatorio"}, status=400)
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.estado in ("entregado", "cancelado"):
        return JsonResponse({"ok": False, "error": "No se puede cancelar"}, status=400)
    with transaction.atomic():
        pedido.estado = "cancelado"
        pedido.motivo_cancelacion = motivo
        pedido.save(update_fields=["estado", "motivo_cancelacion"])
        Auditoria.objects.create(
            accion="Pedido cancelado por mesero",
            detalle=f"Pedido #{pedido.pk}. Motivo: {motivo}",
            empleado=request.user,
            mesa=pedido.sesion.mesa,
            pedido=pedido,
        )
    return JsonResponse({"ok": True})
