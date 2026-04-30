import json
import uuid
import secrets
from decimal import Decimal, InvalidOperation
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.decorators import mesero_requerido
from apps.mesas.models import Mesa, SesionCliente, AlertaMesero
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador, SolicitudPago
from apps.catalogs.models import MetodoPago, EstadoSolicitud, ModalidadIngreso
from apps.menu.models import Producto


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
    mesas = Mesa.objects.prefetch_related(
        "sesiones__pedidos",
        "sesiones__solicitudes_pago__estado_solicitud",
        "alertas",
    ).order_by("numero_mesa")

    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    alertas_count = AlertaMesero.objects.filter(atendida=False).count()

    data = []
    for m in mesas:
        sesiones_activas = [s for s in m.sesiones.all() if s.estado == "activa"]
        pedidos_en_cocina = 0
        pedidos_listos = 0
        tiene_solicitud = False
        tiene_alerta_ayuda = any(not a.atendida for a in m.alertas.all())

        for s in sesiones_activas:
            for p in s.pedidos.all():
                if p.estado in ("recibido", "preparando"):
                    pedidos_en_cocina += 1
                elif p.estado == "listo":
                    pedidos_listos += 1
            for sol in s.solicitudes_pago.all():
                if sol.estado_solicitud.descripcion == "pendiente":
                    tiene_solicitud = True
                    break

        if m.estado == "libre":
            estado_visual = "libre"
        elif tiene_alerta_ayuda:
            estado_visual = "alerta"
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
            "ubicacion": m.ubicacion.nombre if m.ubicacion else "",
            "capacidad": m.capacidad,
            "pin": m.pin_actual or "",
            "clientes": len(sesiones_activas),
            "pedidos_cocina": pedidos_en_cocina,
            "pedidos_listos": pedidos_listos,
            "tiene_solicitud": tiene_solicitud,
            "tiene_alerta_ayuda": tiene_alerta_ayuda,
        })
    return JsonResponse({
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "mesas": data,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
        "alertas_count": alertas_count,
    })


@require_GET
@mesero_requerido
def detalle_mesa(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    sesiones = mesa.sesiones.filter(estado="activa").order_by("fecha_inicio")

    sesiones_data = []
    for s in sesiones:
        pedidos_sesion = s.pedidos.exclude(estado="cancelado").prefetch_related(
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

    solicitudes = []
    for s in sesiones:
        for sol in s.solicitudes_pago.filter(estado_solicitud__descripcion="pendiente").order_by("-fecha_hora"):
            solicitudes.append({
                "id": sol.pk,
                "alias": s.alias,
                "sesion_id": s.pk,
                "tipo": sol.tipo,
                "tipo_display": sol.get_tipo_display(),
                "total": float(sol.total_mesa or sol.total_individual or 0),
                "fecha": sol.fecha_hora.strftime("%H:%M"),
            })

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

    from apps.auditoria.models import Auditoria
    with transaction.atomic():
        mesa.sesiones.filter(estado="activa").update(estado="cerrada")
        mesa.estado = "libre"
        mesa.pin_actual = None
        mesa.save(update_fields=["estado", "pin_actual"])
        Auditoria.objects.create(
            accion="Mesa cerrada",
            detalle=f"Mesa {mesa.numero_mesa} cerrada manualmente por mesero.",
            empleado=request.user,
            mesa=mesa,
        )
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
    """POST — crea un pedido asistido a nombre de una sesión específica."""
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

    from apps.menu.models import OpcionModificador
    from apps.pedidos.utils import aplicar_promociones

    items_norm = []
    mods_map = {}
    for item in items:
        producto = get_object_or_404(Producto, pk=item.get("producto_id"), disponible=True)
        cantidad = int(item.get("cantidad", 1))
        modificadores_ids = item.get("modificadores", [])
        notas = item.get("notas", "")
        precio_extra = sum(
            op.precio_extra
            for op in OpcionModificador.objects.filter(pk__in=modificadores_ids)
        )
        subtotal = (producto.precio + precio_extra) * cantidad
        items_norm.append({
            "producto_id": producto.pk,
            "cantidad": cantidad,
            "modificadores": modificadores_ids,
            "notas": notas,
            "subtotal": subtotal,
        })
        mods_map[producto.pk] = modificadores_ids

    items_norm, _ = aplicar_promociones(items_norm, sesion)

    with transaction.atomic():
        pedido = Pedido.objects.create(
            sesion=sesion,
            modalidad=modalidad_asistido,
            empleado_entrega=request.user,
        )
        for item in items_norm:
            producto = get_object_or_404(Producto, pk=item["producto_id"], disponible=True)
            detalle = DetallePedido.objects.create(
                pedido=pedido, producto=producto,
                cantidad=item["cantidad"],
                notas=item.get("notas", ""),
                subtotal_calculado=item["subtotal"],
                promocion_id=item.get("promocion_id"),
            )
            for op_id in mods_map.get(producto.pk, []):
                try:
                    opcion = OpcionModificador.objects.get(pk=op_id)
                    DetalleModificador.objects.create(
                        detalle=detalle, opcion=opcion,
                        precio_extra_aplicado=opcion.precio_extra,
                        nombre_opcion_historico=opcion.nombre_opcion,
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
    alertas_ayuda = AlertaMesero.objects.filter(
        atendida=False
    ).select_related("mesa", "sesion").order_by("-fecha_creacion")
    listos_count = Pedido.objects.filter(estado="listo").count()
    return render(request, "mesero/mapa_mesas.html", {
        "solicitudes": solicitudes,
        "alertas_ayuda": alertas_ayuda,
        "vista": "alertas",
        "listos_count": listos_count,
    })


@mesero_requerido
def cuentas(request):
    return alertas(request)


@require_POST
@mesero_requerido
def solicitar_cuenta_mesero(request):
    """POST JSON {mesa_id, sesion_id (opcional), tipo ('individual'|'grupal')}"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    mesa_id   = data.get("mesa_id")
    sesion_id = data.get("sesion_id") or None
    tipo      = data.get("tipo", "grupal" if not sesion_id else "individual")

    mesa = get_object_or_404(Mesa, pk=mesa_id)
    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")

    sesion_obj = None
    total_individual = None
    total_mesa = None

    if sesion_id:
        sesion_obj = get_object_or_404(SesionCliente, pk=sesion_id, mesa=mesa, estado="activa")
        pedidos_sesion = sesion_obj.pedidos.prefetch_related("detalles").exclude(estado="cancelado")
        total_individual = sum(
            sum(d.subtotal_calculado for d in p.detalles.all()) for p in pedidos_sesion
        )
        tipo = "individual"
    else:
        sesiones_activas = mesa.sesiones.filter(estado="activa")
        if not sesiones_activas.exists():
            return JsonResponse({"ok": False, "error": "La mesa no tiene sesiones activas."}, status=400)
        total_mesa = sum(
            sum(d.subtotal_calculado for d in p.detalles.all())
            for s in sesiones_activas
            for p in s.pedidos.prefetch_related("detalles").exclude(estado="cancelado")
        )
        tipo = "grupal"

    with transaction.atomic():
        sol, created = SolicitudPago.objects.get_or_create(
            mesa=mesa,
            sesion=sesion_obj,
            estado_solicitud=estado_pendiente,
            defaults={
                "tipo": tipo,
                "total_individual": total_individual,
                "total_mesa": total_mesa,
                "propina_sugerida": round((total_individual or total_mesa or 0) * 10 / 100, 2),
            }
        )

    return JsonResponse({
        "ok": True,
        "created": created,
        "solicitud_id": sol.pk,
        "mensaje": "Solicitud de cuenta creada." if created else "Ya existe una solicitud pendiente para esta mesa.",
    })


@require_POST
@mesero_requerido
def agregar_sesion_asistida(request):
    """POST JSON {mesa_id, alias} — crea una SesionCliente asistida."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    mesa_id = data.get("mesa_id")
    alias = (data.get("alias") or "").strip()

    if not mesa_id or not alias:
        return JsonResponse({"ok": False, "error": "mesa_id y alias son obligatorios"}, status=400)

    mesa = get_object_or_404(Mesa, pk=mesa_id)
    modalidad_asistido, _ = ModalidadIngreso.objects.get_or_create(descripcion="asistido")

    token = str(uuid.uuid4())

    with transaction.atomic():
        primera_sesion = not mesa.sesiones.filter(estado="activa").exists()
        sesion = SesionCliente.objects.create(
            alias=alias,
            token_cookie=token,
            mesa=mesa,
            modalidad_ingreso=modalidad_asistido,
            estado="activa",
        )
        if primera_sesion:
            pin = str(secrets.randbelow(9000) + 1000)
            mesa.pin_actual = pin
            mesa.estado = "ocupada"
            mesa.save(update_fields=["pin_actual", "estado"])

    return JsonResponse({
        "ok": True,
        "sesion_id": sesion.pk,
        "alias": sesion.alias,
        "pin": mesa.pin_actual or "",
    })


@require_POST
@mesero_requerido
def atender_alerta(request):
    """Marca una AlertaMesero como atendida."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    alerta_id = data.get("alerta_id")
    alerta = get_object_or_404(AlertaMesero, pk=alerta_id)
    alerta.atendida = True
    alerta.save(update_fields=["atendida"])
    return JsonResponse({"ok": True})


# ─── Pago ─────────────────────────────────────────────────────────────────────

@mesero_requerido
def pago(request):
    mesa_id = request.GET.get("mesa")
    sesion_id = request.GET.get("sesion")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None
    metodos = MetodoPago.objects.all()
    total = 0
    pedidos_mesa = []

    if mesa:
        if sesion_id:
            sesiones = mesa.sesiones.filter(pk=sesion_id, estado="activa")
        else:
            sesiones = mesa.sesiones.filter(estado="activa")
        for s in sesiones:
            for p in s.pedidos.prefetch_related("detalles__producto").exclude(estado="cancelado"):
                pedidos_mesa.append(p)
                total += sum(d.subtotal_calculado for d in p.detalles.all())
    else:
        sesiones = []

    return render(request, "mesero/pago.html", {
        "mesa": mesa, "sesiones": sesiones,
        "pedidos": pedidos_mesa, "total": total, "metodos": metodos,
        "sesion_id": sesion_id or "",
    })


@require_POST
@mesero_requerido
def procesar_pago(request):
    mesa_id   = request.POST.get("mesa_id")
    metodo_id = request.POST.get("metodo_pago_id")
    sesion_id = request.POST.get("sesion_id") or None
    monto_str = request.POST.get("monto_recibido", "").strip()
    propina_str = request.POST.get("propina", "").strip()

    mesa = get_object_or_404(Mesa, pk=mesa_id)

    if not metodo_id:
        from django.contrib import messages
        messages.error(request, "Debe seleccionar un método de pago.")
        return redirect(f"/mesero/pago/?mesa={mesa_id}")

    metodo = get_object_or_404(MetodoPago, pk=metodo_id)

    if sesion_id:
        sesion_obj = get_object_or_404(SesionCliente, pk=sesion_id, mesa=mesa)
        if sesion_obj.estado != "activa":
            from django.contrib import messages
            messages.error(request, f"Esta sesión ya fue procesada (estado: {sesion_obj.estado}). No se puede cobrar dos veces.")
            return redirect("mesero:mapa_mesas")
        total = DetallePedido.objects.filter(
            pedido__sesion=sesion_obj
        ).exclude(pedido__estado="cancelado").aggregate(
            t=Sum("subtotal_calculado")
        )["t"] or Decimal("0.00")
    else:
        sesiones_activas = mesa.sesiones.filter(estado="activa")
        if not sesiones_activas.exists():
            from django.contrib import messages
            messages.error(request, "Esta mesa no tiene sesiones activas.")
            return redirect("mesero:mapa_mesas")
        total = DetallePedido.objects.filter(
            pedido__sesion__in=sesiones_activas
        ).exclude(pedido__estado="cancelado").aggregate(
            t=Sum("subtotal_calculado")
        )["t"] or Decimal("0.00")

    propina = Decimal("0.00")
    if propina_str:
        try:
            propina = Decimal(propina_str)
            if propina < 0:
                propina = Decimal("0.00")
        except InvalidOperation:
            propina = Decimal("0.00")

    total_con_propina = total + propina

    if monto_str:
        try:
            monto_recibido = Decimal(monto_str)
        except InvalidOperation:
            from django.contrib import messages
            messages.error(request, "El monto recibido no es un número válido.")
            redir = f"/mesero/pago/?mesa={mesa_id}"
            if sesion_id:
                redir += f"&sesion={sesion_id}"
            return redirect(redir)

        if monto_recibido < total_con_propina:
            from django.contrib import messages
            faltante = total_con_propina - monto_recibido
            messages.error(request, f"Monto insuficiente. Faltan ${faltante:.2f} para completar el pago.")
            redir = f"/mesero/pago/?mesa={mesa_id}"
            if sesion_id:
                redir += f"&sesion={sesion_id}"
            return redirect(redir)

    estado_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")

    with transaction.atomic():
        if sesion_id:
            sesion_locked = (
                SesionCliente.objects
                .select_for_update(nowait=False)
                .filter(pk=sesion_id, mesa=mesa)
                .first()
            )
            if sesion_locked is None or sesion_locked.estado != "activa":
                from django.contrib import messages
                messages.error(request, "Esta sesión ya fue procesada por otro usuario. Operación cancelada.")
                return redirect("mesero:mapa_mesas")

            SolicitudPago.objects.filter(
                sesion=sesion_locked,
                estado_solicitud__descripcion="pendiente"
            ).update(estado_solicitud=estado_procesada, metodo_pago=metodo, propina_sugerida=propina)
            sesion_locked.estado = "pagada"
            sesion_locked.save(update_fields=["estado"])

            if not mesa.sesiones.filter(estado="activa").exists():
                mesa.estado = "libre"
                mesa.pin_actual = None
                mesa.save(update_fields=["estado", "pin_actual"])
        else:
            sesiones_locked = list(
                mesa.sesiones
                .select_for_update(nowait=False)
                .filter(estado="activa")
            )
            if not sesiones_locked:
                from django.contrib import messages
                messages.error(request, "La mesa ya no tiene sesiones activas.")
                return redirect("mesero:mapa_mesas")

            for s in sesiones_locked:
                SolicitudPago.objects.filter(
                    sesion=s,
                    estado_solicitud__descripcion="pendiente"
                ).update(estado_solicitud=estado_procesada, metodo_pago=metodo, propina_sugerida=propina)
                s.estado = "pagada"
                s.save(update_fields=["estado"])

            mesa.estado = "libre"
            mesa.pin_actual = None
            mesa.save(update_fields=["estado", "pin_actual"])

    # Registrar pago en Auditoría
    from apps.auditoria.models import Auditoria
    Auditoria.objects.create(
        accion="Pago procesado",
        detalle=(
            f"Mesa {mesa.numero_mesa} | "
            f"{'Sesión #' + str(sesion_id) if sesion_id else 'Todas las sesiones'} | "
            f"Método: {metodo} | Total: ${total:.2f} | Propina: ${propina:.2f}"
        ),
        empleado=request.user,
        mesa=mesa,
    )
    return redirect("mesero:mapa_mesas")


@require_GET
@mesero_requerido
def productos_json(request):
    productos = Producto.objects.filter(disponible=True).prefetch_related(
        "grupos_modificadores__opciones"
    ).order_by("nombre")
    data = []
    for p in productos:
        grupos = []
        for g in p.grupos_modificadores.all():
            grupos.append({
                "id": g.id,
                "nombre": g.nombre_grupo,
                "tipo": g.tipo,
                "es_obligatorio": g.es_obligatorio,
                "max_selecciones": g.max_selecciones,
                "opciones": [
                    {"id": op.id, "nombre": op.nombre_opcion, "precio_extra": float(op.precio_extra)}
                    for op in g.opciones.filter(activo=True)
                ],
            })
        data.append({
            "id": p.id,
            "nombre": p.nombre,
            "precio": float(p.precio),
            "grupos_modificadores": grupos,
        })
    return JsonResponse({"ok": True, "productos": data})


@require_POST
@mesero_requerido
def cancelar_pedido(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    from apps.auditoria.models import Auditoria
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

# ─── Cancelar solicitud de pago ───────────────────────────────────────────────

@require_POST
@mesero_requerido
def cancelar_solicitud_pago(request):
    """
    POST JSON {solicitud_id}
    Cancela una SolicitudPago pendiente con select_for_update para evitar
    condiciones de carrera (doble cancelación simultánea).
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    solicitud_id = data.get("solicitud_id")
    if not solicitud_id:
        return JsonResponse({"ok": False, "error": "solicitud_id requerido"}, status=400)

    from apps.auditoria.models import Auditoria

    with transaction.atomic():
        try:
            solicitud = (
                SolicitudPago.objects
                .select_for_update(nowait=True)
                .select_related("estado_solicitud", "mesa", "sesion")
                .get(pk=solicitud_id)
            )
        except SolicitudPago.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Solicitud no encontrada"}, status=404)
        except Exception:
            # nowait lanza exception si hay lock — otro proceso ya la está modificando
            return JsonResponse({"ok": False, "error": "La solicitud está siendo procesada. Intenta de nuevo."}, status=409)

        if solicitud.estado_solicitud.descripcion != "pendiente":
            return JsonResponse({
                "ok": False,
                "error": f"No se puede cancelar: la solicitud está en estado '{solicitud.estado_solicitud.descripcion}'."
            }, status=400)

        estado_cancelada, _ = EstadoSolicitud.objects.get_or_create(descripcion="cancelada")
        solicitud.estado_solicitud = estado_cancelada
        solicitud.save(update_fields=["estado_solicitud"])

        Auditoria.objects.create(
            accion="Solicitud de pago cancelada",
            detalle=(
                f"Solicitud #{solicitud.pk} (mesa {solicitud.mesa.numero_mesa if solicitud.mesa else 'N/A'}) "
                f"cancelada por mesero. Tipo: {solicitud.tipo}. "
                f"Total: ${solicitud.total_mesa or solicitud.total_individual or 0:.2f}"
            ),
            empleado=request.user,
            mesa=solicitud.mesa,
            solicitud_pago=solicitud,
        )

    return JsonResponse({"ok": True, "mensaje": "Solicitud cancelada correctamente."})


# ─── Editar pedido por mesero (solo estado 'recibido') ────────────────────────

@mesero_requerido
def editar_pedido_mesero(request, pedido_id):
    """
    GET  → devuelve JSON con detalles editables del pedido.
    POST → aplica cambios de cantidad y notas (solo si estado='recibido').

    Restricciones:
    - Solo pedidos en estado 'recibido' (aún no tomados por cocina).
    - Solo se modifican cantidad y notas. No se añaden ni eliminan ítems.
    - El subtotal se recalcula usando el precio unitario implícito del detalle
      (subtotal_calculado / cantidad), preservando el precio histórico original.
    - Los cambios se registran en Auditoría ítem por ítem.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    if pedido.estado != "recibido":
        return JsonResponse({
            "ok": False,
            "error": f"Solo se pueden editar pedidos en estado 'recibido'. Este está en '{pedido.get_estado_display()}'."
        }, status=400)

    if request.method == "GET":
        detalles = pedido.detalles.select_related("producto").prefetch_related("modificadores__opcion")
        data = {
            "ok": True,
            "pedido_id": pedido.pk,
            "estado": pedido.estado,
            "items": [
                {
                    "detalle_id": d.pk,
                    "producto_nombre": d.producto.nombre,
                    "cantidad": d.cantidad,
                    "notas": d.notas or "",
                    "subtotal": float(d.subtotal_calculado),
                    # precio unitario histórico implícito
                    "precio_unitario": float(d.subtotal_calculado / d.cantidad) if d.cantidad else 0,
                    "modificadores": [m.nombre_display for m in d.modificadores.all()],
                }
                for d in detalles
            ],
        }
        return JsonResponse(data)

    # POST
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    cambios = data.get("cambios", [])  # [{detalle_id, cantidad, notas}]
    if not cambios:
        return JsonResponse({"ok": False, "error": "No se enviaron cambios"}, status=400)

    from apps.auditoria.models import Auditoria
    from decimal import Decimal

    registros_auditoria = []

    with transaction.atomic():
        # Re-verificar estado bajo lock
        pedido_locked = Pedido.objects.select_for_update().get(pk=pedido_id)
        if pedido_locked.estado != "recibido":
            return JsonResponse({
                "ok": False,
                "error": "El pedido ya no está en estado 'recibido'. No se puede editar."
            }, status=400)

        for cambio in cambios:
            try:
                detalle = pedido_locked.detalles.select_related("producto").get(pk=cambio["detalle_id"])
            except DetallePedido.DoesNotExist:
                continue

            nueva_cantidad = int(cambio.get("cantidad", detalle.cantidad))
            nuevas_notas = cambio.get("notas", detalle.notas or "").strip()

            if nueva_cantidad < 1:
                return JsonResponse({
                    "ok": False,
                    "error": f"La cantidad para '{detalle.producto.nombre}' debe ser al menos 1."
                }, status=400)

            cantidad_anterior = detalle.cantidad
            notas_anteriores = detalle.notas or ""
            subtotal_anterior = detalle.subtotal_calculado

            if nueva_cantidad != cantidad_anterior or nuevas_notas != notas_anteriores:
                # Precio unitario histórico: nunca usamos Producto.precio
                precio_unitario = detalle.subtotal_calculado / Decimal(str(cantidad_anterior))
                nuevo_subtotal = precio_unitario * Decimal(str(nueva_cantidad))

                detalle.cantidad = nueva_cantidad
                detalle.notas = nuevas_notas
                detalle.subtotal_calculado = nuevo_subtotal
                detalle.save(update_fields=["cantidad", "notas", "subtotal_calculado"])

                registros_auditoria.append(
                    f"  • {detalle.producto.nombre}: "
                    f"qty {cantidad_anterior}→{nueva_cantidad}, "
                    f"subtotal ${subtotal_anterior:.2f}→${nuevo_subtotal:.2f}"
                    + (f", notas: '{notas_anteriores}'→'{nuevas_notas}'" if notas_anteriores != nuevas_notas else "")
                )

        if registros_auditoria:
            Auditoria.objects.create(
                accion="Pedido editado por mesero",
                detalle=f"Pedido #{pedido_id} modificado:\n" + "\n".join(registros_auditoria),
                empleado=request.user,
                mesa=pedido_locked.sesion.mesa,
                pedido=pedido_locked,
            )

    return JsonResponse({"ok": True, "mensaje": "Pedido actualizado correctamente."})
