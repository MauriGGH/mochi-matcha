"""
Panel del mesero — vistas principales.

Cubre el ciclo completo de atención de mesa:
  - Autenticación (login/logout con rol mesero/gerente/admin).
  - Mapa de mesas en tiempo real (polling cada 3 s vía mesas_estado).
  - Detalle de mesa: sesiones activas, pedidos y solicitudes de pago.
  - Pedido asistido: el mesero hace pedidos a nombre de una sesión.
  - Gestión de pedidos: entregar, cancelar, editar (solo en estado 'recibido').
  - Cobro: procesar_pago (efectivo/tarjeta/mixto), flujo PayPal, tickets.
  - Alertas: solicitudes de atención y de cobro pendientes.
"""

import json
import uuid
import secrets
from decimal import Decimal, InvalidOperation
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.decorators import mesero_requerido
from apps.mesas.models import Mesa, SesionCliente, AlertaMesero
from apps.pedidos.models import Pedido, DetallePedido, DetalleModificador, SolicitudPago
from apps.catalogs.models import MetodoPago, EstadoSolicitud, ModalidadIngreso
from apps.menu.models import Producto


# ─── Auth ─────────────────────────────────────────────────────────────────────

@never_cache
@ensure_csrf_cookie
def login_mesero(request):
    """
    Muestra y procesa el formulario de login del mesero.

    GET  → renderiza la plantilla de login con cookie CSRF garantizada.
    POST → autentica al usuario; solo se permite el acceso si el rol es
           mesero, gerente o admin y la cuenta está activa.
    Si el usuario ya está autenticado con el rol correcto, redirige
    directamente al mapa de mesas (evita mostrar el login de nuevo).

    Parámetros:
        request (HttpRequest): petición HTTP.
    Retorno:
        HttpResponse: redirige a mapa_mesas si el login es exitoso;
                      renderiza el formulario con mensaje de error si falla.
    """
    if request.user.is_authenticated and request.user.rol in ("mesero", "gerente", "admin"):
        return redirect("mesero:mapa_mesas")
    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, usuario=usuario, password=contrasena)
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
    """
    Cierra la sesión del mesero y redirige al login.

    Parámetros:
        request (HttpRequest): petición HTTP.
    Retorno:
        HttpResponseRedirect: redirige a mesero:login_mesero.
    """
    logout(request)
    return redirect("mesero:login_mesero")


# ─── Mapa de mesas ────────────────────────────────────────────────────────────

@mesero_requerido
def mapa_mesas(request):
    """
    Renderiza la vista principal del panel del mesero: el mapa de mesas.

    Pasa al template:
      - mesas: todas las mesas ordenadas para construir el grid inicial;
        el polling JS las actualiza en tiempo real.
      - listos_count / solicitudes_count: contadores para los badges del topbar.
      - categorias: árbol completo de menú con modificadores, usado por el
        modal de pedido asistido.
      - metodos_pago_json: JSON embebido para el modal de pago (evita hardcodear
        métodos en JS; incluye PayPal y cualquier método nuevo del catálogo).

    Parámetros:
        request (HttpRequest): petición HTTP autenticada como mesero.
    Retorno:
        HttpResponse: plantilla mesero/mapa_mesas.html con el contexto anterior.
    """
    from apps.menu.models import Categoria
    mesas = Mesa.objects.prefetch_related("sesiones").order_by("numero_mesa")
    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    categorias = Categoria.objects.prefetch_related(
        "productos__grupos_modificadores__opciones"
    ).filter(productos__disponible=True).distinct()
    # FIX #2/#3 — métodos de pago dinámicos para el modal (antes hardcoded).
    # Esto permite que PayPal (y cualquier método nuevo agregado al catálogo)
    # aparezca automáticamente sin tocar el JS. Se serializa con json.dumps
    # para que el template lo embeba como JSON válido.
    metodos_pago_json = json.dumps(list(MetodoPago.objects.all().values("id", "descripcion")))
    return render(request, "mesero/mapa_mesas.html", {
        "mesas": mesas,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
        "categorias": categorias,
        "metodos_pago_json": metodos_pago_json,
    })


@require_GET
@mesero_requerido
def mesas_estado(request):
    """
    Endpoint de polling: devuelve el estado visual actualizado de todas las mesas.

    El JS del template llama a este endpoint cada 3 segundos para actualizar
    los tiles del mapa sin recargar la página. La respuesta incluye:
      - estado_visual: clasificación derivada (libre/alerta/cobrando/listo/cocina/ocupada).
      - listos_count, solicitudes_count, alertas_count: para los badges globales.
      - ts: timestamp del servidor (ms) para descartar respuestas fuera de orden.

    Parámetros:
        request (HttpRequest): petición GET autenticada.
    Retorno:
        JsonResponse: {"ok": True, "mesas": [...], "listos_count": N, ...}
    """
    mesas = Mesa.objects.prefetch_related(
        "sesiones__pedidos",
        # Solicitudes a nivel de MESA: incluye las grupales (sesion=None) que
        # antes no se veían al recorrer solo sesiones__solicitudes_pago.
        "solicitudes_pago__estado_solicitud",
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

        # Solicitudes pendientes de la mesa (individuales + grupales)
        for sol in m.solicitudes_pago.all():
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
            "nota_cierre": m.nota_cierre or "",
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
    """
    Devuelve el detalle completo de una mesa para el panel lateral del mapa.

    Incluye sesiones activas con sus pedidos e ítems, solicitudes de pago
    pendientes (individuales y grupales) y el total acumulado de la mesa.
    Este endpoint es llamado por selectMesa() en el JS del mapa.

    Parámetros:
        request (HttpRequest): petición GET autenticada.
        mesa_id (int): PK de la mesa a consultar.
    Retorno:
        JsonResponse: {"ok": True, "sesiones": [...], "solicitudes": [...], ...}
    """
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    sesiones = mesa.sesiones.filter(estado="activa").order_by("fecha_inicio")

    sesiones_data = []
    for s in sesiones:
        pedidos_sesion = s.pedidos.exclude(estado="cancelado").prefetch_related(
            "detalles__producto", "detalles__modificadores__opcion", "detalles__promocion"
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
                            "subtotal_bruto": float(
                                (d.producto.precio + sum(
                                    m.precio_extra_aplicado for m in d.modificadores.all()
                                )) * d.cantidad
                            ),
                            "notas": d.notas or "",
                            "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
                            "promo_aplicada": d.promocion.titulo if d.promocion else None,
                        }
                        for d in p.detalles.all()
                    ],
                }
                for p in pedidos_sesion
            ],
        })

    # Solicitudes pendientes de la mesa: individuales (sesion != None) +
    # grupales (sesion == None, ligadas solo a la mesa). Antes solo se
    # recorrían las de cada sesión, por lo que las grupales no aparecían.
    solicitudes = []
    solicitudes_qs = (
        SolicitudPago.objects
        .filter(mesa=mesa, estado_solicitud__descripcion="pendiente")
        .select_related("sesion")
        .order_by("-fecha_hora")
    )
    for sol in solicitudes_qs:
        if sol.tipo == "grupal":
            total = float(sol.total_mesa or 0)
            alias = "Toda la mesa"
            sesion_id = None
        else:
            total = float(sol.total_individual or sol.total_mesa or 0)
            alias = sol.sesion.alias if sol.sesion else ""
            sesion_id = sol.sesion_id
        solicitudes.append({
            "id": sol.pk,
            "alias": alias,
            "sesion_id": sesion_id,
            "tipo": sol.tipo,
            "tipo_display": sol.get_tipo_display(),
            "total": total,
            "fecha": sol.fecha_hora.strftime("%H:%M"),
            "metodo_pref": sol.detalle_pago or "",
        })

    total_mesa = sum(s["total"] for s in sesiones_data)

    return JsonResponse({
        "ok": True,
        "mesa_libre": mesa.estado == "libre",
        "mesa_id": mesa.pk,
        "numero_mesa": mesa.numero_mesa,
        "pin": mesa.pin_actual or "",
        "estado": mesa.estado,
        "nota_cierre": mesa.nota_cierre or "",
        "sesiones": sesiones_data,
        "solicitudes": solicitudes,
        "total_mesa": total_mesa,
    })


# ─── Pedidos ──────────────────────────────────────────────────────────────────

@require_GET
@mesero_requerido
def pedidos_listos_json(request):
    """JSON para polling de la vista listos; devuelve pedidos estado='listo' con items."""
    pedidos = (
        Pedido.objects.filter(estado="listo")
        .select_related("sesion__mesa")
        .prefetch_related("detalles__producto")
        .order_by("fecha_hora_ingreso")
    )
    data = [
        {
            "id": p.pk,
            "mesa": p.sesion.mesa.numero_mesa,
            "alias": p.sesion.alias,
            "items": [
                {"cantidad": d.cantidad, "nombre": d.producto.nombre, "subtotal": str(d.subtotal_calculado)}
                for d in p.detalles.all()
            ],
        }
        for p in pedidos
    ]
    return JsonResponse({
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "pedidos": data,
        "count": len(data),
    })


@mesero_requerido
def pedidos_listos(request):
    """
    Renderiza la vista de pedidos listos para entregar.

    Reutiliza la plantilla mapa_mesas.html con vista='listos' para mostrar
    únicamente los pedidos en estado 'listo'. El mesero puede marcarlos
    como entregados desde esta vista.

    Parámetros:
        request (HttpRequest): petición HTTP autenticada.
    Retorno:
        HttpResponse: plantilla mesero/mapa_mesas.html con vista='listos'.
    """
    pedidos = Pedido.objects.filter(estado="listo").select_related(
        "sesion__mesa"
    ).prefetch_related("detalles__producto").order_by("fecha_hora_ingreso")
    metodos_pago_json = json.dumps(list(MetodoPago.objects.all().values("id", "descripcion")))
    return render(request, "mesero/mapa_mesas.html", {
        "pedidos_listos": pedidos, "vista": "listos",
        "listos_count": pedidos.count(),
        "metodos_pago_json": metodos_pago_json,
    })


@require_POST
@mesero_requerido
def entregar_pedido(request):
    """
    Marca un pedido como entregado al cliente.

    Recibe JSON {pedido_id}. Registra el empleado que entregó y la hora.
    El JS elimina la tarjeta del pedido de la vista sin recargar la página.

    Parámetros:
        request (HttpRequest): petición POST con body JSON.
    Retorno:
        JsonResponse: {"ok": True} si tiene éxito, {"ok": False} si falla.
    """
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
    """
    Cierra una SesionCliente activa y libera la mesa si ya no quedan sesiones.

    Recibe JSON {sesion_id}. Usa select_for_update para evitar condiciones de
    carrera cuando dos meseros cierran la misma sesión simultáneamente.
    Si la sesión ya estaba cerrada, responde con ya_cerrada=True sin error.
    Libera la mesa (estado='libre', pin=None) cuando no quedan sesiones activas.

    Parámetros:
        request (HttpRequest): petición POST con body JSON.
    Retorno:
        JsonResponse: {"ok": True} o {"ok": False, "error": "..."}.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)
    # P8: bloquear la sesión y re-validar su estado dentro de la transacción.
    with transaction.atomic():
        sesion = (
            SesionCliente.objects
            .select_for_update()
            .filter(pk=data.get("sesion_id"))
            .first()
        )
        if sesion is None:
            return JsonResponse({"ok": False, "error": "Sesión no encontrada."}, status=404)
        if sesion.estado != "activa":
            return JsonResponse({"ok": True, "ya_cerrada": True})
        sesion.estado = "cerrada"
        sesion.save(update_fields=["estado"])
        mesa = Mesa.objects.select_for_update().get(pk=sesion.mesa_id)
        if not mesa.sesiones.filter(estado="activa").exists():
            mesa.estado = "libre"
            mesa.pin_actual = None
            mesa.save(update_fields=["estado", "pin_actual"])
    return JsonResponse({"ok": True})


def _post_pago_mesa(mesa, user=None):
    """
    Tras procesar un pago, NO libera la mesa automáticamente: solo limpia el PIN
    (para que no se acepten nuevos clientes) y registra una AlertaMesero con el
    estado de la mesa. El mesero debe usar el botón "Cerrar mesa" (cerrar_mesa)
    para liberarla cuando lo decida.

    Si ya no quedan sesiones activas → la mesa está lista para cerrar.
    Si quedan sesiones activas con consumo → indica cuánto falta cobrar.
    """
    from apps.mesas.models import AlertaMesero
    sesiones_activas = list(mesa.sesiones.filter(estado="activa"))

    if not sesiones_activas:
        # Todo cobrado. Solo falta el cierre manual del mesero.
        nota = "Cuenta saldada — lista para cerrar"
        mensaje = (
            f"Mesa {mesa.numero_mesa} pagada — lista para cerrar. "
            f"Usa el botón 'Cerrar mesa' para liberarla."
        )
        mesa.nota_cierre = nota
        if mesa.pin_actual:
            mesa.pin_actual = None
        mesa.save(update_fields=["nota_cierre", "pin_actual"])
    else:
        # Quedan clientes en la mesa con consumo no cobrado: el mesero debe
        # decidir si cobra el resto o cierra manualmente la mesa con esa nota.
        pendiente = DetallePedido.objects.filter(
            pedido__sesion__in=sesiones_activas,
        ).exclude(pedido__estado="cancelado").aggregate(
            t=Sum("subtotal_calculado"),
        )["t"] or Decimal("0.00")
        nota = f"Queda ${pendiente:.2f} sin cobrar ({len(sesiones_activas)} sesión(es) activa(s))"
        mensaje = (
            f"Mesa {mesa.numero_mesa} con cobros parciales — quedan "
            f"{len(sesiones_activas)} sesión(es) activa(s) "
            f"con ${pendiente:.2f} pendiente(s) de cobro."
        )
        mesa.nota_cierre = nota
        mesa.save(update_fields=["nota_cierre"])

    AlertaMesero.objects.create(
        mesa=mesa, tipo="personalizado", mensaje=mensaje,
    )


@require_POST
@mesero_requerido
def cerrar_mesa(request):
    """
    Cierra todas las sesiones activas de una mesa y la marca como libre.

    Recibe JSON {mesa_id}. Operación atómica: cierra sesiones en bulk y
    registra la acción en Auditoría. Usar solo cuando se requiere cerrar la
    mesa entera sin procesar cobro (p. ej., mesa vacía sin consumo).

    Parámetros:
        request (HttpRequest): petición POST con body JSON.
    Retorno:
        JsonResponse: {"ok": True} o {"ok": False} si el JSON es inválido.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False}, status=400)
    mesa = get_object_or_404(Mesa, pk=data.get("mesa_id"))

    from apps.auditoria.models import Auditoria
    with transaction.atomic():
        mesa.sesiones.filter(estado__in=["activa", "pagada"]).update(estado="cerrada")
        mesa.estado = "libre"
        mesa.pin_actual = None
        mesa.nota_cierre = ""
        mesa.save(update_fields=["estado", "pin_actual", "nota_cierre"])
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
    """
    POST — crea un Pedido asistido a nombre de una SesionCliente específica.

    Recibe JSON:
        {sesion_id, items: [{producto_id, cantidad, modificadores, notas}],
         promocion_id (opcional), idempotency_key (opcional)}

    Flujo:
      1. Validación rápida de idempotencia antes de la transacción (P1).
      2. Resolución de modificadores y cálculo de subtotales.
      3. Aplicación de promociones vía aplicar_promociones().
      4. Transacción atómica con segunda verificación de idempotencia bajo lock.
      5. Creación de Pedido → DetallePedido → DetalleModificador.

    Parámetros:
        request (HttpRequest): petición POST con body JSON.
    Retorno:
        JsonResponse: {"ok": True, "pedido_id": N} o {"ok": False, "error": "..."}.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    sesion_id = data.get("sesion_id")
    items = data.get("items", [])
    idempotency_key = data.get("idempotency_key") or None

    if not sesion_id or not items:
        return JsonResponse({"ok": False, "error": "Datos incompletos"}, status=400)

    # Idempotencia (P1): si este token ya generó un pedido, devolverlo sin
    # duplicar (doble-click / reintento del mesero).
    if idempotency_key:
        ya_existe = Pedido.objects.filter(token_idempotencia=idempotency_key).first()
        if ya_existe is not None:
            return JsonResponse({"ok": True, "pedido_id": ya_existe.pk, "duplicado": True})

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

    # BUGFIX (problema 1): el cuerpo de esta petición es JSON, no form-encoded,
    # por lo que request.POST está vacío y promocion_id siempre era None. Cuando
    # el carrito tenía más de una promoción elegible, aplicar_promociones espera
    # una elección explícita que nunca llegaba → no se aplicaba NINGUNA promo.
    # Ahora se lee del JSON ya parseado (data).
    promo_id_meseros = data.get("promocion_id") or None
    items_norm, _, _ = aplicar_promociones(items_norm, sesion, promocion_id=promo_id_meseros)

    with transaction.atomic():
        # Re-chequear idempotencia dentro de la transacción por si dos requests
        # del mesero entraron casi a la vez.
        if idempotency_key:
            ya_existe = Pedido.objects.filter(token_idempotencia=idempotency_key).first()
            if ya_existe is not None:
                return JsonResponse({"ok": True, "pedido_id": ya_existe.pk, "duplicado": True})
        pedido = Pedido.objects.create(
            sesion=sesion,
            modalidad=modalidad_asistido,
            empleado_entrega=request.user,
            token_idempotencia=idempotency_key or None,
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
    """
    Renderiza la vista de alertas y solicitudes pendientes.

    Muestra dos secciones:
      - Solicitudes de atención (AlertaMesero.atendida=False): el cliente pide
        ayuda al mesero pulsando el botón de atención en su dispositivo.
      - Solicitudes de cobro (SolicitudPago pendientes): el cliente solicitó
        la cuenta desde su dispositivo o el mesero la generó manualmente.

    Parámetros:
        request (HttpRequest): petición HTTP autenticada.
    Retorno:
        HttpResponse: plantilla mesero/mapa_mesas.html con vista='alertas'.
    """
    solicitudes = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).select_related("mesa", "sesion").order_by("-fecha_hora")
    alertas_ayuda = AlertaMesero.objects.filter(
        atendida=False
    ).select_related("mesa", "sesion").order_by("-fecha_creacion")
    listos_count = Pedido.objects.filter(estado="listo").count()
    metodos_pago_json = json.dumps(list(MetodoPago.objects.all().values("id", "descripcion")))
    return render(request, "mesero/mapa_mesas.html", {
        "solicitudes": solicitudes,
        "alertas_ayuda": alertas_ayuda,
        "vista": "alertas",
        "listos_count": listos_count,
        "metodos_pago_json": metodos_pago_json,
    })


@mesero_requerido
def cuentas(request):
    """
    Alias de la vista alertas(). La URL /cuentas/ es un sinónimo semántico
    para acceder a las solicitudes de cobro pendientes desde el sidebar.

    Parámetros:
        request (HttpRequest): petición HTTP autenticada.
    Retorno:
        HttpResponse: delega en alertas() con su misma respuesta.
    """
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
        # Bloquear la fila de la mesa y re-leer su estado dentro de la transacción
        # para evitar race conditions con el flujo de cierre simultáneo.
        mesa = Mesa.objects.select_for_update().get(pk=mesa_id)

        # No permitir agregar personas si la mesa está en proceso de cierre:
        # (a) tiene sesiones pagadas pendientes de cerrar, o
        # (b) tiene nota_cierre (pago saldado o cierre parcial en curso).
        if mesa.estado != "libre" and (
            bool(mesa.nota_cierre) or
            mesa.sesiones.filter(estado="pagada").exists()
        ):
            return JsonResponse({
                "ok": False,
                "error": "La mesa está en proceso de cierre. Ciérrala primero antes de agregar nuevos comensales.",
            }, status=409)

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
    """
    Renderiza la página de cobro dedicada (mesero/pago.html).

    Recibe mesa y sesion opcionales via query string:
      - ?mesa=<id>          → cobro grupal de toda la mesa.
      - ?mesa=<id>&sesion=<id> → cobro individual de una sesión.
    Excluye PayPal del listado de métodos porque ese flujo lo gestiona el cliente
    desde su dispositivo (paypal_crear_orden / paypal_capturar).
    total_js se pasa como float sin formato locale para que JS lo use directamente.

    Parámetros:
        request (HttpRequest): petición GET autenticada.
    Retorno:
        HttpResponse: plantilla mesero/pago.html con el contexto de cobro.
    """
    mesa_id = request.GET.get("mesa")
    sesion_id = request.GET.get("sesion")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None
    # Excluir PayPal — es un flujo del cliente, no del mesero
    metodos = MetodoPago.objects.exclude(descripcion__iexact="PayPal")
    total = Decimal("0.00")
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
        "pedidos": pedidos_mesa, "total": total,
        "total_js": float(total),   # sin formato locale — para JS
        "metodos": metodos,
        "sesion_id": sesion_id or "",
    })


@require_GET
@mesero_requerido
def total_cobro(request):
    """
    Devuelve el total a cobrar RECALCULADO en vivo desde la BD (P2).
    El modal de pago lo consulta al abrirse para no mostrar un monto viejo si
    el cliente agregó pedidos después de solicitar la cuenta.
    Params: mesa (id), sesion (id opcional → individual; ausente → toda la mesa).
    """
    mesa_id   = request.GET.get("mesa")
    sesion_id = request.GET.get("sesion") or None
    mesa = get_object_or_404(Mesa, pk=mesa_id)

    if sesion_id:
        total = DetallePedido.objects.filter(
            pedido__sesion_id=sesion_id, pedido__sesion__mesa=mesa,
        ).exclude(pedido__estado="cancelado").aggregate(
            t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")
    else:
        total = DetallePedido.objects.filter(
            pedido__sesion__mesa=mesa, pedido__sesion__estado="activa",
        ).exclude(pedido__estado="cancelado").aggregate(
            t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

    return JsonResponse({"ok": True, "total": float(total)})


@require_POST
@mesero_requerido
def procesar_pago(request):
    """
    Procesa el cobro de una mesa o sesión y redirige al ticket.

    Recibe datos de formulario (form-encoded desde pago.html o el modal):
        mesa_id, metodo_pago_id, sesion_id (opcional), monto_recibido (efectivo),
        propina, monto_efectivo y monto_tarjeta (pago mixto).

    Flujo:
      1. Validación de "cuenta ya saldada" mediante SesionCliente.estado.
      2. Cálculo del total desde la BD (fuente de verdad, no desde el form).
      3. Validación de montos según el método (efectivo/mixto).
      4. Transacción atómica con select_for_update para evitar doble cobro.
      5. Marcado de sesión(es) como 'pagada' y cierre de mesa si procede.
      6. Registro de auditoría y redirección a ver_ticket.

    Parámetros:
        request (HttpRequest): petición POST form-encoded autenticada.
    Retorno:
        HttpResponseRedirect: redirige a mesero:ver_ticket con el ID de la solicitud.
    """
    mesa_id            = request.POST.get("mesa_id")
    metodo_id          = request.POST.get("metodo_pago_id")
    sesion_id          = request.POST.get("sesion_id") or None
    monto_str          = request.POST.get("monto_recibido", "").strip()
    propina_str        = request.POST.get("propina", "").strip()
    monto_efectivo_str = request.POST.get("monto_efectivo", "").strip()
    monto_tarjeta_str  = request.POST.get("monto_tarjeta", "").strip()

    mesa = get_object_or_404(Mesa, pk=mesa_id)

    def _volver_pago(msg):
        from django.contrib import messages as _m
        _m.error(request, msg)
        return redirect("mesero:mapa_mesas")

    if not metodo_id:
        return _volver_pago("Debe seleccionar un método de pago.")

    metodo = get_object_or_404(MetodoPago, pk=metodo_id)
    desc = metodo.descripcion.upper()

    # ── Validación de "cuenta ya saldada" (problema 1) ────────────────────────
    # La fuente de verdad es SesionCliente.estado. Una sesión "pagada"/"cerrada"
    # no puede volver a cobrarse. Para grupal, debe quedar al menos una sesión
    # activa; si no, la mesa ya fue saldada.
    if sesion_id:
        sesion_obj = get_object_or_404(SesionCliente, pk=sesion_id, mesa=mesa)
        if sesion_obj.estado != "activa":
            return _volver_pago(
                f"La cuenta de {sesion_obj.alias} ya fue saldada "
                f"(estado: {sesion_obj.get_estado_display()}). No se puede cobrar de nuevo."
            )
        total = DetallePedido.objects.filter(
            pedido__sesion=sesion_obj
        ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")
    else:
        sesiones_activas = mesa.sesiones.filter(estado="activa")
        if not sesiones_activas.exists():
            return _volver_pago(
                "La cuenta de esta mesa ya fue saldada — no quedan sesiones activas. "
                "No se puede cobrar de nuevo."
            )
        total = DetallePedido.objects.filter(
            pedido__sesion__in=sesiones_activas
        ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

    propina = Decimal("0.00")
    if propina_str:
        try:
            propina = max(Decimal("0.00"), Decimal(propina_str))
        except InvalidOperation:
            propina = Decimal("0.00")

    total_con_propina = total + propina

    # Campos de detalle de pago según el método
    monto_recibido = None
    monto_efectivo = None
    monto_tarjeta  = None
    cambio         = Decimal("0.00")

    if "MIXTO" in desc:
        try:
            monto_efectivo = max(Decimal("0.00"), Decimal(monto_efectivo_str or "0"))
        except InvalidOperation:
            monto_efectivo = Decimal("0.00")
        try:
            monto_tarjeta = max(Decimal("0.00"), Decimal(monto_tarjeta_str or "0"))
        except InvalidOperation:
            monto_tarjeta = Decimal("0.00")
        if monto_efectivo + monto_tarjeta < total_con_propina:
            faltante = total_con_propina - monto_efectivo - monto_tarjeta
            return _volver_pago(f"Monto insuficiente en pago mixto. Faltan ${faltante:.2f}.")
        detalle_pago = "MIXTO"
    elif "EFECTIVO" in desc:
        if monto_str:
            try:
                monto_recibido = Decimal(monto_str)
            except InvalidOperation:
                return _volver_pago("El monto recibido no es un número válido.")
            if monto_recibido < total_con_propina:
                faltante = total_con_propina - monto_recibido
                return _volver_pago(f"Monto insuficiente. Faltan ${faltante:.2f} para completar el pago.")
            cambio = monto_recibido - total_con_propina
        detalle_pago = "EFECTIVO"
    elif "PAYPAL" in desc:
        detalle_pago = "PAYPAL"
    else:
        detalle_pago = "TARJETA"

    estado_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")

    with transaction.atomic():
        if sesion_id:
            sesion_locked = (
                SesionCliente.objects
                .select_for_update(nowait=False)
                .filter(pk=sesion_id, mesa=mesa)
                .first()
            )
            # Re-validación bajo lock: nadie pudo haberla cobrado entre el
            # check inicial y aquí.
            if sesion_locked is None or sesion_locked.estado != "activa":
                return _volver_pago("Esta cuenta ya fue saldada por otro usuario. Operación cancelada.")

            sol, _ = SolicitudPago.objects.get_or_create(
                sesion=sesion_locked,
                estado_solicitud=estado_pendiente,
                defaults={"mesa": mesa, "tipo": "individual", "total_individual": total},
            )
            sol.estado_solicitud = estado_procesada
            sol.metodo_pago      = metodo
            sol.propina_sugerida = propina
            sol.detalle_pago     = detalle_pago
            sol.monto_recibido   = monto_recibido
            sol.cambio           = cambio
            sol.monto_efectivo   = monto_efectivo
            sol.monto_tarjeta    = monto_tarjeta
            sol.save()

            sesion_locked.estado = "pagada"
            sesion_locked.save(update_fields=["estado"])

            # E1: registrar la sesión cubierta (uniformidad con el flujo grupal).
            sol.sesiones_cubiertas.set([sesion_locked])

            # Cerrar cualquier otra solicitud pendiente de ESTA sesión para que
            # no quede colgando y no se pueda volver a cobrar.
            SolicitudPago.objects.filter(
                sesion=sesion_locked, estado_solicitud=estado_pendiente
            ).exclude(pk=sol.pk).update(estado_solicitud=estado_procesada)

            # 1.1: no liberar la mesa automáticamente — solo registrar el
            # estado en una AlertaMesero. El mesero la cierra manualmente.
            _post_pago_mesa(mesa, request.user)
        else:
            sesiones_locked = list(
                mesa.sesiones
                .select_for_update(nowait=False)
                .filter(estado="activa")
            )
            # Re-validación bajo lock (problema 1): si ya no hay sesiones
            # activas, la mesa fue saldada por otro usuario.
            if not sesiones_locked:
                return _volver_pago("La cuenta de esta mesa ya fue saldada. Operación cancelada.")

            # La SolicitudPago grupal se crea con sesion=None y mesa=mesa.
            # P4: usar filter().first() en vez de get_or_create — si por datos
            # antiguos hubiera más de una pendiente, get_or_create lanzaría
            # MultipleObjectsReturned. Tomamos la primera y las demás se cierran
            # más abajo junto con el resto de pendientes de la mesa.
            sol = (
                SolicitudPago.objects
                .filter(mesa=mesa, sesion=None, estado_solicitud=estado_pendiente)
                .order_by("fecha_hora")
                .first()
            )
            if sol is None:
                sol = SolicitudPago.objects.create(
                    mesa=mesa, sesion=None,
                    estado_solicitud=estado_pendiente,
                    tipo="grupal", total_mesa=total,
                )
            sol.estado_solicitud = estado_procesada
            sol.metodo_pago      = metodo
            sol.propina_sugerida = propina
            sol.detalle_pago     = detalle_pago
            sol.monto_recibido   = monto_recibido
            sol.cambio           = cambio
            sol.monto_efectivo   = monto_efectivo
            sol.monto_tarjeta    = monto_tarjeta
            sol.total_mesa       = total
            sol.save()

            # BUGFIX (problema 1): cerrar TODAS las sesiones activas de la mesa,
            # no solo la del solicitante.
            sesiones_ids = [s.pk for s in sesiones_locked]
            for s in sesiones_locked:
                s.estado = "pagada"
                s.save(update_fields=["estado"])

            # E1: registrar QUÉ sesiones cubrió esta solicitud grupal para que
            # el ticket reconstruya solo los pedidos de esta visita.
            sol.sesiones_cubiertas.set(sesiones_locked)

            # Cerrar TODAS las solicitudes pendientes de la mesa (grupales e
            # individuales de cualquier sesión) — la mesa quedó saldada.
            SolicitudPago.objects.filter(
                mesa=mesa, estado_solicitud=estado_pendiente
            ).exclude(pk=sol.pk).update(estado_solicitud=estado_procesada)
            SolicitudPago.objects.filter(
                sesion__in=sesiones_ids, estado_solicitud=estado_pendiente
            ).update(estado_solicitud=estado_procesada)

            # 1.1: no liberar la mesa automáticamente — registrar nota y dejar
            # que el mesero la cierre manualmente con "Cerrar mesa".
            _post_pago_mesa(mesa, request.user)

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
    return redirect("mesero:ver_ticket", sol.pk)


@require_GET
@mesero_requerido
def productos_json(request):
    """
    Devuelve el catálogo de productos disponibles en formato JSON.

    Incluye los grupos de modificadores con sus opciones activas y precios
    extra. El modal de pedido asistido llama a este endpoint al abrirse para
    construir el selector de productos dinámicamente en el cliente.

    Parámetros:
        request (HttpRequest): petición GET autenticada.
    Retorno:
        JsonResponse: {"ok": True, "productos": [{id, nombre, precio,
                       grupos_modificadores: [{...opciones...}]}]}
    """
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
    """
    Cancela un pedido que aún no fue entregado ni cancelado.

    Recibe JSON {pedido_id, motivo}. El motivo es obligatorio para la trazabilidad.
    No permite cancelar pedidos en estado 'entregado' o ya 'cancelado'.
    Registra la cancelación en Auditoría con el motivo indicado.

    Parámetros:
        request (HttpRequest): petición POST con body JSON autenticada.
    Retorno:
        JsonResponse: {"ok": True} o {"ok": False, "error": "..."}.
    """
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


@require_POST
@mesero_requerido
def limpiar_notificaciones(request):
    """
    POST — limpia en bulk las notificaciones que sea seguro descartar.

    Reglas:
      - AlertaMesero no atendidas → se marcan atendida=True (siempre seguro).
      - SolicitudPago pendientes cuya sesión ya está pagada/cerrada, o cuya
        mesa ya está libre → se cancelan con registro de auditoría (la solicitud
        quedó huérfana porque el cobro ya fue procesado por otra vía).
      - SolicitudPago pendientes con sesión todavía activa → NO se tocan;
        se devuelve el conteo para que el mesero las gestione manualmente.
    """
    from apps.auditoria.models import Auditoria

    with transaction.atomic():
        # 1. Alertas de atención — marcar todas como atendidas en bulk
        alertas_limpiadas = AlertaMesero.objects.filter(atendida=False).update(atendida=True)

        # 2. Solicitudes de cobro pendientes
        pendientes = list(
            SolicitudPago.objects
            .filter(estado_solicitud__descripcion="pendiente")
            .select_related("estado_solicitud", "mesa", "sesion")
            .select_for_update(skip_locked=True)
        )

        estado_cancelada, _ = EstadoSolicitud.objects.get_or_create(descripcion="cancelada")
        solicitudes_limpiadas = 0
        solicitudes_pendientes = 0

        for sol in pendientes:
            # ¿La solicitud ya está resuelta (sesión pagada/cerrada o mesa libre)?
            sesion_resuelta = (
                sol.sesion is None or
                sol.sesion.estado in ("pagada", "cerrada")
            )
            mesa_libre = sol.mesa is None or sol.mesa.estado == "libre"

            if sesion_resuelta or mesa_libre:
                sol.estado_solicitud = estado_cancelada
                sol.save(update_fields=["estado_solicitud"])
                Auditoria.objects.create(
                    accion="Solicitud de pago cancelada (limpieza)",
                    detalle=(
                        f"Solicitud #{sol.pk} (mesa {sol.mesa.numero_mesa if sol.mesa else 'N/A'}) "
                        f"descartada en limpieza bulk — sesión ya {sol.sesion.estado if sol.sesion else 'sin sesión'} "
                        f"o mesa libre. Tipo: {sol.tipo}. "
                        f"Total: ${sol.total_mesa or sol.total_individual or 0:.2f}"
                    ),
                    empleado=request.user,
                    mesa=sol.mesa,
                    solicitud_pago=sol,
                )
                solicitudes_limpiadas += 1
            else:
                solicitudes_pendientes += 1

    return JsonResponse({
        "ok": True,
        "alertas_limpiadas": alertas_limpiadas,
        "solicitudes_limpiadas": solicitudes_limpiadas,
        "solicitudes_pendientes": solicitudes_pendientes,
    })


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


# ---------------------------------------------------------------------------
# PayPal helpers
# ---------------------------------------------------------------------------

def _paypal_base(modo):
    """
    Devuelve la URL base de la API de PayPal según el modo de operación.

    Parámetros:
        modo (str): 'live' para producción, cualquier otro valor para sandbox.
    Retorno:
        str: URL base de la API REST de PayPal.
    """
    return "https://api-m.paypal.com" if modo == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_cfg(key, default=""):
    """Lee la clave PayPal: Configuracion en BD primero, luego settings (env).
    Permite que el gerente edite credenciales desde el panel sin redeploy.
    """
    from django.conf import settings
    from apps.gerente.models import Configuracion
    obj = Configuracion.objects.filter(clave=key).first()
    if obj and obj.valor:
        return obj.valor
    setting_map = {
        "paypal_client_id": getattr(settings, "PAYPAL_CLIENT_ID", ""),
        "paypal_secret":    getattr(settings, "PAYPAL_SECRET", ""),
        "paypal_modo":      getattr(settings, "PAYPAL_MODO", "sandbox"),
    }
    return setting_map.get(key, default)


def _paypal_access_token(client_id, secret, modo):
    """
    Obtiene un Bearer token de OAuth2 desde la API de PayPal.

    Usa autenticación HTTP Basic con las credenciales de la aplicación.
    El token resultante tiene una vida corta (~9 h) y se obtiene en cada
    llamada que lo necesita (sin caché, para simplicidad).

    Parámetros:
        client_id (str): Client ID de la app PayPal.
        secret    (str): Client Secret de la app PayPal.
        modo      (str): 'live' o 'sandbox'.
    Retorno:
        str: access_token listo para usar en el header Authorization: Bearer.
    """
    import urllib.request as urlreq
    import urllib.parse
    from base64 import b64encode

    credentials = b64encode(f"{client_id}:{secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urlreq.Request(
        f"{_paypal_base(modo)}/v1/oauth2/token",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlreq.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


# ---------------------------------------------------------------------------
# PayPal views
# ---------------------------------------------------------------------------

@require_POST
@mesero_requerido
def paypal_crear_orden(request):
    """
    Crea una orden de pago en PayPal y devuelve su ID al cliente JS.

    El JS del modal de pago llama a este endpoint para iniciar el flujo PayPal.
    Calcula el total real desde la BD (no confía en el monto del cliente).
    Requiere que PayPal esté configurado (client_id + secret) o devuelve 503.

    Recibe JSON {mesa_id, sesion_id (opcional)}.
    Retorno:
        JsonResponse: {"ok": True, "order_id": "..."} o {"ok": False, "error": "..."}.
    """
    import urllib.request as urlreq

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    mesa_id   = data.get("mesa_id")
    sesion_id = data.get("sesion_id") or None

    if not mesa_id:
        return JsonResponse({"ok": False, "error": "mesa_id requerido"}, status=400)

    mesa = get_object_or_404(Mesa, pk=mesa_id)

    if sesion_id:
        sesion_obj = get_object_or_404(SesionCliente, pk=sesion_id, mesa=mesa)
        total = DetallePedido.objects.filter(
            pedido__sesion=sesion_obj
        ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")
    else:
        sesiones_activas = mesa.sesiones.filter(estado="activa")
        total = DetallePedido.objects.filter(
            pedido__sesion__in=sesiones_activas
        ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

    client_id = _paypal_cfg("paypal_client_id")
    secret    = _paypal_cfg("paypal_secret")
    modo      = _paypal_cfg("paypal_modo", "sandbox")

    if not client_id or not secret:
        return JsonResponse({"ok": False, "error": "PayPal no está configurado en el sistema."}, status=503)

    try:
        access_token = _paypal_access_token(client_id, secret, modo)
        order_body = json.dumps({
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "MXN",
                    "value": str(total.quantize(Decimal("0.01"))),
                }
            }]
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
        return JsonResponse({"ok": False, "error": f"Error al comunicarse con PayPal: {exc}"}, status=502)

    return JsonResponse({"ok": True, "order_id": order["id"]})


@require_POST
@mesero_requerido
def paypal_capturar(request):
    """
    Captura un pago aprobado en PayPal y lo registra en la BD como procesado.

    Recibe JSON {order_id, mesa_id, sesion_id (opcional)}.
    Flujo:
      1. Valida el estado de la sesión/mesa ANTES de capturar en PayPal (E4):
         si ya está saldada no se realiza la captura, evitando cobrar dinero real
         sin poder aplicarlo.
      2. Captura la orden vía API PayPal. Si el status no es COMPLETED → error.
      3. Transacción atómica: marca sesión(es) como 'pagada', crea o actualiza
         SolicitudPago, registra sesiones_cubiertas (E1), libera la mesa.
      4. Registra auditoría y devuelve la URL del ticket.

    Parámetros:
        request (HttpRequest): petición POST con body JSON autenticada.
    Retorno:
        JsonResponse: {"ok": True, "solicitud_id": N, "ticket_url": "..."}
                      o {"ok": False, "error": "..."}.
    """
    import urllib.request as urlreq
    from django.urls import reverse
    import urllib.request as urlreq

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    order_id  = data.get("order_id", "").strip()
    mesa_id   = data.get("mesa_id")
    sesion_id = data.get("sesion_id") or None

    if not order_id or not mesa_id:
        return JsonResponse({"ok": False, "error": "order_id y mesa_id son requeridos"}, status=400)

    mesa = get_object_or_404(Mesa, pk=mesa_id)

    # E4: validar el estado ANTES de capturar en PayPal. Si la cuenta ya está
    # saldada, rechazar aquí — capturar primero y rechazar después cobraría
    # dinero real sin aplicarlo.
    if sesion_id:
        sesion_obj = get_object_or_404(SesionCliente, pk=sesion_id, mesa=mesa)
        if sesion_obj.estado != "activa":
            return JsonResponse({
                "ok": False,
                "error": f"La cuenta de {sesion_obj.alias} ya fue saldada.",
            }, status=409)
    else:
        if not mesa.sesiones.filter(estado="activa").exists():
            return JsonResponse({
                "ok": False,
                "error": "La cuenta de esta mesa ya fue saldada.",
            }, status=409)

    client_id = _paypal_cfg("paypal_client_id")
    secret    = _paypal_cfg("paypal_secret")
    modo      = _paypal_cfg("paypal_modo", "sandbox")

    if not client_id or not secret:
        return JsonResponse({"ok": False, "error": "PayPal no está configurado en el sistema."}, status=503)

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
        return JsonResponse({"ok": False, "error": f"Error al capturar el pago: {exc}"}, status=502)

    if capture.get("status") != "COMPLETED":
        return JsonResponse({"ok": False, "error": "El pago no fue completado en PayPal."}, status=402)

    metodo_paypal   = MetodoPago.objects.filter(descripcion="PayPal").first()
    estado_procesada, _ = EstadoSolicitud.objects.get_or_create(descripcion="procesada")
    estado_pendiente, _ = EstadoSolicitud.objects.get_or_create(descripcion="pendiente")

    with transaction.atomic():
        if sesion_id:
            sesion_locked = (
                SesionCliente.objects
                .select_for_update(nowait=False)
                .filter(pk=sesion_id, mesa=mesa)
                .first()
            )
            if sesion_locked is None:
                return JsonResponse({"ok": False, "error": "Sesión no encontrada."}, status=404)
            # E4: no permitir recobrar una sesión ya saldada vía PayPal.
            if sesion_locked.estado != "activa":
                return JsonResponse({
                    "ok": False,
                    "error": f"La cuenta de {sesion_locked.alias} ya fue saldada.",
                }, status=409)

            total = DetallePedido.objects.filter(
                pedido__sesion=sesion_locked
            ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

            sol, _ = SolicitudPago.objects.get_or_create(
                mesa=mesa,
                sesion=sesion_locked,
                estado_solicitud=estado_pendiente,
                defaults={"tipo": "individual", "total_individual": total},
            )
            sol.estado_solicitud  = estado_procesada
            sol.metodo_pago       = metodo_paypal
            sol.referencia_externa = order_id
            sol.detalle_pago      = "PAYPAL"
            sol.save(update_fields=["estado_solicitud", "metodo_pago", "referencia_externa", "detalle_pago"])

            sesion_locked.estado = "pagada"
            sesion_locked.save(update_fields=["estado"])
            sol.sesiones_cubiertas.set([sesion_locked])  # E1

            # 1.1: no liberar la mesa automáticamente
            _post_pago_mesa(mesa, request.user)
        else:
            sesiones_locked = list(
                mesa.sesiones
                .select_for_update(nowait=False)
                .filter(estado="activa")
            )
            if not sesiones_locked:
                return JsonResponse({"ok": False, "error": "La cuenta de esta mesa ya fue saldada."}, status=409)

            total = DetallePedido.objects.filter(
                pedido__sesion__in=sesiones_locked
            ).exclude(pedido__estado="cancelado").aggregate(t=Sum("subtotal_calculado"))["t"] or Decimal("0.00")

            sol = None
            for s in sesiones_locked:
                existing = SolicitudPago.objects.filter(
                    sesion=s, estado_solicitud=estado_pendiente
                ).first()
                if existing:
                    existing.estado_solicitud  = estado_procesada
                    existing.metodo_pago       = metodo_paypal
                    existing.referencia_externa = order_id
                    existing.detalle_pago      = "PAYPAL"
                    existing.save(update_fields=["estado_solicitud", "metodo_pago", "referencia_externa", "detalle_pago"])
                    if sol is None:
                        sol = existing
                s.estado = "pagada"
                s.save(update_fields=["estado"])

            if sol is None:
                sol = SolicitudPago.objects.create(
                    mesa=mesa,
                    tipo="grupal",
                    total_mesa=total,
                    estado_solicitud=estado_procesada,
                    metodo_pago=metodo_paypal,
                    referencia_externa=order_id,
                    detalle_pago="PAYPAL",
                )
            sol.sesiones_cubiertas.set(sesiones_locked)  # E1

            # 1.1: no liberar la mesa automáticamente
            _post_pago_mesa(mesa, request.user)

    from apps.auditoria.models import Auditoria
    Auditoria.objects.create(
        accion="Pago PayPal procesado",
        detalle=(
            f"Mesa {mesa.numero_mesa} | "
            f"{'Sesión #' + str(sesion_id) if sesion_id else 'Todas las sesiones'} | "
            f"Orden PayPal: {order_id} | Total: ${total:.2f}"
        ),
        empleado=request.user,
        mesa=mesa,
    )

    return JsonResponse({
        "ok": True,
        "solicitud_id": sol.pk,
        "ticket_url": reverse("mesero:ver_ticket", args=[sol.pk]),
    })


# ---------------------------------------------------------------------------
# Ticket views
# ---------------------------------------------------------------------------

def _ticket_context(sol, user):
    """
    Construye el contexto de plantilla para mostrar o imprimir un ticket.

    Recopila los pedidos cubiertos por la SolicitudPago usando la estrategia E1:
      1. sesiones_cubiertas (M2M explícito, guardado al procesar el pago).
      2. Fallback a sol.sesion para solicitudes individuales viejas.
      3. Fallback a sesiones activas/pagadas de la mesa para grupales sin registro.

    Calcula el desglose financiero (E3):
      - subtotal_bruto: precio de lista × cantidad + extras de modificadores.
      - descuento_total: diferencia entre precio de lista y subtotal_calculado
        (que ya incorpora descuentos de promociones aplicadas).
      - total_final: subtotal_bruto - descuento_total + propina.

    Parámetros:
        sol  (SolicitudPago): solicitud cuyo ticket se va a generar.
        user (CustomUser): mesero autenticado (aparece en el ticket).
    Retorno:
        dict: contexto listo para pasar a render() o render_to_string().
    """
    from apps.gerente.models import Configuracion

    def cfg(k, default=""):
        obj = Configuracion.objects.filter(clave=k).first()
        return obj.valor if obj else default

    # E1: reconstruir los pedidos SOLO de las sesiones que esta solicitud cubrió.
    #   1) sesiones_cubiertas (registro explícito hecho al procesar el pago);
    #   2) si no hay (solicitudes viejas / aún pendientes), se cae a sol.sesion
    #      para individuales, o a las sesiones de la mesa para grupales.
    sesiones_cubiertas = list(sol.sesiones_cubiertas.all())
    if sesiones_cubiertas:
        pedidos = list(
            Pedido.objects.filter(sesion__in=sesiones_cubiertas)
            .prefetch_related("detalles__producto", "detalles__modificadores")
            .exclude(estado="cancelado")
        )
    elif sol.sesion_id:
        pedidos = list(
            sol.sesion.pedidos
            .prefetch_related("detalles__producto", "detalles__modificadores")
            .exclude(estado="cancelado")
        )
    elif sol.mesa_id:
        # Respaldo para solicitudes grupales sin sesiones registradas: limitar a
        # las sesiones pagadas/activas de la mesa (no todo el histórico).
        pedidos = list(
            Pedido.objects.filter(
                sesion__mesa_id=sol.mesa_id,
                sesion__estado__in=("activa", "pagada"),
            )
            .prefetch_related("detalles__producto", "detalles__modificadores")
            .exclude(estado="cancelado")
        )
    else:
        pedidos = []

    # E3: desglosar el descuento real. subtotal_calculado YA trae el precio con
    # promoción aplicada; el precio de lista es precio del producto × cantidad
    # más los extras de modificadores. La diferencia es el descuento.
    subtotal_bruto  = Decimal("0.00")
    descuento_total = Decimal("0.00")
    for p in pedidos:
        for d in p.detalles.all():
            extras = sum(
                (m.precio_extra_aplicado or Decimal("0.00"))
                for m in d.modificadores.all()
            )
            precio_lista = (d.producto.precio * d.cantidad) + extras
            subtotal_bruto  += precio_lista
            descuento_total += (precio_lista - d.subtotal_calculado)

    if descuento_total < 0:
        descuento_total = Decimal("0.00")

    propina     = sol.propina_sugerida or Decimal("0.00")
    # El template muestra: Subtotal (bruto) − Descuento + Propina = TOTAL
    total_final = subtotal_bruto - descuento_total + propina

    restaurante = {
        "nombre":    cfg("restaurante_nombre", "Mochi Matcha"),
        "direccion": cfg("restaurante_direccion"),
        "telefono":  cfg("restaurante_telefono"),
        "rfc":       cfg("restaurante_rfc"),
    }

    return {
        "sol":            sol,
        "mesa":           sol.mesa,
        "mesero":         user,
        "pedidos":        pedidos,
        "restaurante":    restaurante,
        "subtotal":       subtotal_bruto,   # precio de lista, antes de promos
        "descuento_total": descuento_total,
        "propina":        propina,
        "total_final":    total_final,
    }


@mesero_requerido
def ver_ticket(request, solicitud_id):
    """
    Muestra el ticket de una solicitud de pago ya procesada.

    Parámetros:
        request        (HttpRequest): petición GET autenticada.
        solicitud_id   (int): PK de la SolicitudPago.
    Retorno:
        HttpResponse: plantilla mesero/ticket.html con el contexto del ticket.
    """
    sol = get_object_or_404(SolicitudPago, pk=solicitud_id)
    return render(request, "mesero/ticket.html", _ticket_context(sol, request.user))


@mesero_requerido
def ticket_pdf(request, solicitud_id):
    """
    Genera y sirve el ticket como PDF usando WeasyPrint.

    Renderiza la misma plantilla que ver_ticket() a string y la convierte a PDF.
    Si WeasyPrint no está instalado, redirige a ver_ticket con un mensaje de error.
    El PDF se sirve inline para que el navegador lo muestre en lugar de forzar
    la descarga, lo que facilita la impresión desde el móvil del mesero.

    Parámetros:
        request        (HttpRequest): petición GET autenticada.
        solicitud_id   (int): PK de la SolicitudPago.
    Retorno:
        HttpResponse (application/pdf) o redirección a ver_ticket si falla.
    """
    from django.http import HttpResponse
    from django.template.loader import render_to_string

    sol = get_object_or_404(SolicitudPago, pk=solicitud_id)
    html_str = render_to_string("mesero/ticket.html", _ticket_context(sol, request.user), request=request)

    try:
        import weasyprint
    except ImportError:
        from django.contrib import messages
        messages.error(request, "WeasyPrint no está instalado.")
        return redirect("mesero:ver_ticket", solicitud_id)

    pdf_bytes = weasyprint.HTML(string=html_str).write_pdf()
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="ticket-{sol.pk:06d}.pdf"'
    return resp
