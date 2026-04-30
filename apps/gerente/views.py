import json
import logging

logger = logging.getLogger(__name__)
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, Coalesce
from django.db.models import DecimalField
from decimal import Decimal
from django.contrib import messages

from apps.accounts.decorators import gerente_requerido
from apps.accounts.models import Empleado
from apps.menu.models import Categoria, Producto, GrupoModificador, OpcionModificador, Promocion, TipoPromocion, TipoDescuento
from apps.mesas.models import Mesa, SesionCliente, UbicacionMesa
from apps.pedidos.models import Pedido, DetallePedido, SolicitudPago
from apps.auditoria.models import Auditoria
from apps.catalogs.models import MetodoPago, EstadoSolicitud
from apps.gerente.models import Configuracion


def login_gerente(request):
    if request.user.is_authenticated and request.user.rol in ("gerente", "admin"):
        return redirect("gerente:dashboard")
    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, username=usuario, password=contrasena)
        if user and user.rol in ("gerente", "admin") and user.is_active:
            login(request, user)
            return redirect("gerente:dashboard")
        error = "Credenciales incorrectas o sin acceso a este módulo."
    return render(request, "base/login.html", {
        "rol": "gerente", "rol_display": "Administrador",
        "form_action": "/gerente/login/", "error": error,
        "usuario_previo": request.POST.get("usuario", ""),
    })


def logout_gerente(request):
    logout(request)
    return redirect("gerente:login_gerente")


# ─── Dashboard / Floor Plan ───────────────────────────────────────────────────

@gerente_requerido
def dashboard(request):
    return redirect("gerente:floor_plan")


@gerente_requerido
def floor_plan(request):
    mesas = Mesa.objects.prefetch_related("sesiones__pedidos").order_by("numero_mesa")
    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    return render(request, "gerente/floor_plan.html", {
        "mesas": mesas,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
    })


@require_GET
@gerente_requerido
def stats_json(request):
    hoy = timezone.now().date()
    pedidos_hoy = Pedido.objects.filter(fecha_hora_ingreso__date=hoy).exclude(estado="cancelado")

    # BUG #4 FIX: reemplaza el doble bucle con Sum() agregado.
    # El código anterior hacía prefetch_related pero luego llamaba .all() dentro
    # del bucle interno, forzando queries adicionales por cada pedido (~N queries).
    # La agregación calcula el total en una sola query SQL.
    ventas_hoy = pedidos_hoy.aggregate(
        total=Sum("detalles__subtotal_calculado")
    )["total"] or 0.0

    return JsonResponse({
        "ventas_hoy": float(ventas_hoy),
        "pedidos_hoy": pedidos_hoy.count(),
        "mesas_ocupadas": Mesa.objects.filter(estado="ocupada").count(),
        "listos_count": Pedido.objects.filter(estado="listo").count(),
        "solicitudes_count": SolicitudPago.objects.filter(
            estado_solicitud__descripcion="pendiente"
        ).count(),
    })


# ─── Detalle de mesa ─────────────────────────────────────────────────────────

@require_GET
@gerente_requerido
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
        for sol in s.solicitudes_pago.filter(estado_solicitud__descripcion="pendiente"):
            solicitudes.append({
                "id": sol.pk,
                "alias": s.alias,
                "tipo": sol.tipo,
                "tipo_display": sol.get_tipo_display(),
                "total": float(sol.total_mesa or sol.total_individual or 0),
                "fecha": sol.fecha_hora.strftime("%H:%M"),
            })

    total_mesa = sum(s["total"] for s in sesiones_data)
    return JsonResponse({
        "ok": True,
        "mesa_id": mesa.pk,
        "numero_mesa": mesa.numero_mesa,
        "pin": mesa.pin_actual or "",
        "estado": mesa.estado,
        "mesa_libre": mesa.estado == "libre",
        "sesiones": sesiones_data,
        "solicitudes": solicitudes,
        "total_mesa": total_mesa,
    })


# ─── Cancelar pedido (solo gerente) ──────────────────────────────────────────

@require_POST
@gerente_requerido
def cancelar_pedido(request):
    """POST JSON: { pedido_id, motivo }"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    pedido_id = data.get("pedido_id")
    motivo = data.get("motivo", "").strip()

    if not motivo:
        return JsonResponse({"ok": False, "error": "El motivo es obligatorio"}, status=400)

    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.estado in ("entregado", "cancelado"):
        return JsonResponse({"ok": False, "error": "No se puede cancelar este pedido"}, status=400)

    pedido.estado = "cancelado"
    pedido.motivo_cancelacion = motivo
    pedido.save(update_fields=["estado", "motivo_cancelacion"])

    Auditoria.objects.create(
        accion="Pedido cancelado",
        detalle=f"Pedido #{pedido.pk} cancelado. Motivo: {motivo}",
        empleado=request.user,
        mesa=pedido.sesion.mesa,
        pedido=pedido,
    )

    return JsonResponse({"ok": True})


# ─── Cancelar solicitud de pago (gerente) ─────────────────────────────────────

@require_POST
@gerente_requerido
def cancelar_solicitud_pago(request):
    """
    POST JSON {solicitud_id}
    Cancela una SolicitudPago pendiente. Usa select_for_update para evitar
    condiciones de carrera.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    solicitud_id = data.get("solicitud_id")
    if not solicitud_id:
        return JsonResponse({"ok": False, "error": "solicitud_id requerido"}, status=400)

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
            accion="Solicitud de pago cancelada (gerente)",
            detalle=(
                f"Solicitud #{solicitud.pk} (mesa {solicitud.mesa.numero_mesa if solicitud.mesa else 'N/A'}) "
                f"cancelada por gerente. Tipo: {solicitud.tipo}. "
                f"Total: ${solicitud.total_mesa or solicitud.total_individual or 0:.2f}"
            ),
            empleado=request.user,
            mesa=solicitud.mesa,
            solicitud_pago=solicitud,
        )

    return JsonResponse({"ok": True, "mensaje": "Solicitud cancelada correctamente."})


# ─── Mesas ────────────────────────────────────────────────────────────────────

@gerente_requerido
def mesas_estado(request):
    """JSON polling para el floor plan del gerente."""
    # BUG #5 FIX: prefetch completo para evitar N+1 queries por polling.
    # Igual que en mesero/views.py, las llamadas anidadas a count()/exists()
    # generaban ~100 queries por cada actualización del floor plan.
    mesas = Mesa.objects.prefetch_related(
        "sesiones__pedidos",
        "sesiones__solicitudes_pago__estado_solicitud",
    ).order_by("numero_mesa")

    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()

    data = []
    for m in mesas:
        sesiones_activas = [s for s in m.sesiones.all() if s.estado == "activa"]
        pedidos_cocina = 0
        pedidos_listos = 0
        tiene_solicitud = False

        for s in sesiones_activas:
            for p in s.pedidos.all():
                if p.estado in ("recibido", "preparando"):
                    pedidos_cocina += 1
                elif p.estado == "listo":
                    pedidos_listos += 1
            for sol in s.solicitudes_pago.all():
                if sol.estado_solicitud.descripcion == "pendiente":
                    tiene_solicitud = True
                    break

        if m.estado == "libre":
            estado_visual = "libre"
        elif tiene_solicitud:
            estado_visual = "cobrando"
        elif pedidos_listos > 0:
            estado_visual = "listo"
        elif pedidos_cocina > 0:
            estado_visual = "cocina"
        else:
            estado_visual = "ocupada"

        data.append({
            "id": m.pk,
            "numero": m.numero_mesa,
            "estado": m.estado,
            "estado_visual": estado_visual,
            "pin": m.pin_actual or "",
            "clientes": len(sesiones_activas),
            "pedidos_cocina": pedidos_cocina,
            "pedidos_listos": pedidos_listos,
            "tiene_solicitud": tiene_solicitud,
        })
    return JsonResponse({
        "ok": True, "mesas": data,
        "listos_count": listos_count,
        "solicitudes_count": solicitudes_count,
    })


@gerente_requerido
def mesas(request):
    return redirect("gerente:mesas_crud")


@gerente_requerido
def mesas_crud(request):
    if request.method == "POST":
        numero = request.POST.get("numero_mesa")
        capacidad = request.POST.get("capacidad", 4)
        ubicacion_id = request.POST.get("ubicacion_id") or None
        import uuid as _uuid
        qr = f"mesa-{numero}-{_uuid.uuid4().hex[:8]}"
        ubicacion_obj = UbicacionMesa.objects.filter(pk=ubicacion_id).first() if ubicacion_id else None
        Mesa.objects.get_or_create(
            numero_mesa=numero,
            defaults={"capacidad": capacidad, "ubicacion": ubicacion_obj, "codigo_qr": qr}
        )
        return redirect("gerente:mesas_crud")

    all_mesas = Mesa.objects.select_related("ubicacion").order_by("numero_mesa")
    meseros = Empleado.objects.filter(rol="mesero", activo=True)
    ubicaciones = UbicacionMesa.objects.order_by("nombre")
    return render(request, "gerente/menu_manager.html", {
        "mesas": all_mesas, "meseros": meseros,
        "ubicaciones": ubicaciones, "vista": "mesas"
    })


@require_POST
@gerente_requerido
def ubicacion_crear(request):
    """AJAX: crea una UbicacionMesa y devuelve JSON {ok, id, nombre}."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    nombre = data.get("nombre", "").strip()
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre es obligatorio"}, status=400)
    obj, created = UbicacionMesa.objects.get_or_create(nombre=nombre)
    return JsonResponse({"ok": True, "id": obj.pk, "nombre": obj.nombre, "created": created})


@require_POST
@gerente_requerido
def ubicacion_editar(request, id):
    """AJAX: edita el nombre de una UbicacionMesa."""
    obj = get_object_or_404(UbicacionMesa, pk=id)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    nombre = data.get("nombre", "").strip()
    if not nombre:
        return JsonResponse({"ok": False, "error": "El nombre es obligatorio"}, status=400)
    obj.nombre = nombre  # save() del modelo aplica .upper()
    obj.save()
    return JsonResponse({"ok": True, "id": obj.pk, "nombre": obj.nombre})


@require_POST
@gerente_requerido
def ubicacion_eliminar(request, id):
    """AJAX: elimina una UbicacionMesa solo si no tiene mesas asociadas."""
    obj = get_object_or_404(UbicacionMesa, pk=id)
    if obj.mesas.exists():
        return JsonResponse(
            {"ok": False, "error": "No se puede eliminar: tiene mesas asociadas."},
            status=400
        )
    obj.delete()
    return JsonResponse({"ok": True})


@require_POST
@gerente_requerido
def mesa_eliminar(request, id):
    mesa = get_object_or_404(Mesa, pk=id)
    if mesa.estado == "libre":
        mesa.delete()
    return redirect("gerente:mesas_crud")


@require_POST
@gerente_requerido
def asignar_mesero(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    mesero_id = request.POST.get("mesero_id")
    if mesero_id:
        mesero = get_object_or_404(Empleado, pk=mesero_id, rol="mesero")
        mesa.id_mesero_asignado = mesero
    else:
        mesa.id_mesero_asignado = None
    mesa.save(update_fields=["id_mesero_asignado"])
    return JsonResponse({"ok": True})


# ─── Productos ────────────────────────────────────────────────────────────────

@gerente_requerido
def productos(request):
    prods = Producto.objects.select_related("categoria").order_by("categoria__orden", "nombre")
    categorias = Categoria.objects.order_by("orden")
    return render(request, "gerente/menu_manager.html", {
        "productos": prods, "categorias": categorias, "vista": "productos"
    })


@gerente_requerido
def productos_nuevo(request):
    categorias = Categoria.objects.order_by("orden")
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        precio = request.POST.get("precio", 0)
        descripcion = request.POST.get("descripcion", "").strip()
        imagen_url = request.POST.get("imagen_url", "").strip()
        categoria_id = request.POST.get("categoria_id")
        disponible = request.POST.get("disponible") == "on"
        cat = get_object_or_404(Categoria, pk=categoria_id)
        Producto.objects.create(
            nombre=nombre, precio=precio, descripcion=descripcion or None,
            imagen_url=imagen_url or None, categoria=cat, disponible=disponible,
        )
        return redirect("gerente:productos")
    return render(request, "gerente/menu_manager.html", {
        "categorias": categorias, "vista": "productos", "form_nuevo": True
    })


@gerente_requerido
def producto_editar(request, id):
    producto = get_object_or_404(Producto, pk=id)
    categorias = Categoria.objects.order_by("orden")
    if request.method == "POST":
        producto.nombre = request.POST.get("nombre", producto.nombre).strip()
        producto.precio = request.POST.get("precio", producto.precio)
        producto.descripcion = request.POST.get("descripcion", "").strip() or None
        producto.imagen_url = request.POST.get("imagen_url", "").strip() or None
        producto.disponible = request.POST.get("disponible") == "on"
        cat_id = request.POST.get("categoria_id")
        if cat_id:
            producto.categoria = get_object_or_404(Categoria, pk=cat_id)
        producto.save()
        return redirect("gerente:productos")
    return render(request, "gerente/menu_manager.html", {
        "producto_editar": producto, "categorias": categorias, "vista": "productos"
    })


@require_POST
@gerente_requerido
def producto_eliminar(request, id):
    producto = get_object_or_404(Producto, pk=id)
    producto.disponible = False
    producto.save(update_fields=["disponible"])
    return JsonResponse({"ok": True})


# ─── Categorías ───────────────────────────────────────────────────────────────

@gerente_requerido
def categorias(request):
    cats = Categoria.objects.order_by("orden")
    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        orden = int(request.POST.get("orden", 0))
        area = request.POST.get("area", "ambos")
        if nombre:
            Categoria.objects.create(nombre=nombre, orden=orden, area=area)
        return redirect("gerente:categorias")
    return render(request, "gerente/menu_manager.html", {
        "categorias": cats, "vista": "categorias"
    })


@require_POST
@gerente_requerido
def categoria_eliminar(request, id):
    cat = get_object_or_404(Categoria, pk=id)
    if not cat.productos.filter(disponible=True).exists():
        cat.delete()
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "Tiene productos activos asociados"}, status=400)


# ─── Modificadores ────────────────────────────────────────────────────────────

@gerente_requerido
def modificadores(request):
    grupos = GrupoModificador.objects.prefetch_related("productos", "opciones").order_by("-pk")
    productos_list = Producto.objects.filter(disponible=True).order_by("nombre")
    plantillas = GrupoModificador.objects.filter(es_plantilla=True).prefetch_related("opciones").order_by("-pk")
    return render(request, "gerente/menu_manager.html", {
        "grupos": grupos, "productos_list": productos_list,
        "plantillas": plantillas, "vista": "modificadores"
    })


@require_POST
@gerente_requerido
def modificador_crear(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False}, status=400)

    opciones = data.get("opciones", [])
    if not opciones:
        return JsonResponse(
            {"ok": False, "error": "Debe agregar al menos una opción al grupo"},
            status=400,
        )

    # Soporta producto_ids (lista M2M) o producto_id (único, retrocompatible)
    producto_ids = data.get("producto_ids") or []
    if not producto_ids:
        single = data.get("producto_id")
        if single:
            producto_ids = [single]

    if not producto_ids:
        return JsonResponse({"ok": False, "error": "Selecciona al menos un producto"}, status=400)

    productos = list(Producto.objects.filter(pk__in=producto_ids, disponible=True))
    if not productos:
        return JsonResponse({"ok": False, "error": "Productos no encontrados"}, status=400)

    grupo = GrupoModificador.objects.create(
        nombre_grupo=data.get("nombre_grupo", "").strip(),
        tipo=data.get("tipo", "única"),
        es_obligatorio=data.get("es_obligatorio", False),
        max_selecciones=data.get("max_selecciones") or None,
    )
    grupo.productos.set(productos)

    for op in opciones:
        OpcionModificador.objects.create(
            nombre_opcion=op.get("nombre", "").strip(),
            precio_extra=op.get("precio_extra", 0),
            grupo=grupo,
        )
    return JsonResponse({"ok": True, "grupo_id": grupo.pk})


@require_POST
@gerente_requerido
def modificador_eliminar(request, id):
    grupo = get_object_or_404(GrupoModificador, pk=id)
    grupo.delete()
    return JsonResponse({"ok": True})


@require_POST
@gerente_requerido
def modificador_toggle_plantilla(request, id):
    """Marca/desmarca un grupo como plantilla reutilizable."""
    grupo = get_object_or_404(GrupoModificador, pk=id)
    grupo.es_plantilla = not grupo.es_plantilla
    grupo.save(update_fields=["es_plantilla"])
    return JsonResponse({"ok": True, "es_plantilla": grupo.es_plantilla})


@require_POST
@gerente_requerido
def modificador_clonar(request):
    """Clona un grupo plantilla añadiéndolo a uno o más productos."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)
    plantilla_id = data.get("plantilla_id")
    producto_ids = data.get("producto_ids") or []
    if not producto_ids:
        single = data.get("producto_id")
        if single:
            producto_ids = [single]
    plantilla = get_object_or_404(GrupoModificador, pk=plantilla_id, es_plantilla=True)
    productos = list(Producto.objects.filter(pk__in=producto_ids, disponible=True))
    if not productos:
        return JsonResponse({"ok": False, "error": "Productos no encontrados"}, status=400)
    nuevo = GrupoModificador.objects.create(
        nombre_grupo=plantilla.nombre_grupo,
        tipo=plantilla.tipo,
        es_obligatorio=plantilla.es_obligatorio,
        max_selecciones=plantilla.max_selecciones,
        es_plantilla=False,
    )
    nuevo.productos.set(productos)
    for op in plantilla.opciones.all():
        op.__class__.objects.create(
            nombre_opcion=op.nombre_opcion,
            precio_extra=op.precio_extra,
            grupo=nuevo,
        )
    return JsonResponse({"ok": True, "grupo_id": nuevo.pk})


@gerente_requerido
def modificador_editar(request, id):
    """
    GET  → devuelve JSON con datos completos del grupo (nombre, tipo, productos, opciones).
    POST → actualiza el grupo usando estrategia upsert segura para opciones:
           - Opciones con 'id' en el payload → se actualizan.
           - Opciones sin 'id' → se crean nuevas.
           - Opciones que ya no están en el payload → se intentan eliminar;
             si tienen usos históricos (ProtectedError) se conservan intactas
             para no romper la integridad referencial de DetalleModificador.
    Justificación: DetalleModificador.opcion usa on_delete=PROTECT; borrar
    opciones usadas lanzaría ProtectedError. Las opciones obsoletas sin usos
    sí se eliminan para mantener el catálogo limpio.
    """
    from django.db import IntegrityError
    from django.db.models import ProtectedError

    grupo = get_object_or_404(GrupoModificador, pk=id)

    if request.method == "GET":
        # Solo opciones activas para el modal de edición; las inactivas son histórico
        opciones = [
            {"id": op.pk, "nombre": op.nombre_opcion, "precio_extra": float(op.precio_extra)}
            for op in grupo.opciones.filter(activo=True)
        ]
        producto_ids = list(grupo.productos.values_list("pk", flat=True))
        return JsonResponse({
            "ok": True,
            "grupo": {
                "id":              grupo.pk,
                "nombre_grupo":    grupo.nombre_grupo,
                "tipo":            grupo.tipo,
                "es_obligatorio":  grupo.es_obligatorio,
                "max_selecciones": grupo.max_selecciones,
                "producto_ids":    producto_ids,
                "opciones":        opciones,
            }
        })

    # ── POST: actualizar ─────────────────────────────────────────────────────
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "JSON inválido"}, status=400)

    opciones_payload = data.get("opciones", [])
    if not opciones_payload:
        return JsonResponse({"ok": False, "error": "Debe agregar al menos una opción"}, status=400)

    producto_ids = data.get("producto_ids") or []
    if not producto_ids:
        single = data.get("producto_id")
        if single:
            producto_ids = [single]
    if not producto_ids:
        return JsonResponse({"ok": False, "error": "Selecciona al menos un producto"}, status=400)

    productos = list(Producto.objects.filter(pk__in=producto_ids, disponible=True))
    if not productos:
        return JsonResponse({"ok": False, "error": "Productos no encontrados"}, status=400)

    with transaction.atomic():
        # 1. Actualizar campos del grupo
        grupo.nombre_grupo    = data.get("nombre_grupo", grupo.nombre_grupo).strip()
        grupo.tipo            = data.get("tipo", grupo.tipo)
        grupo.es_obligatorio  = data.get("es_obligatorio", grupo.es_obligatorio)
        grupo.max_selecciones = data.get("max_selecciones") or None
        grupo.save()

        # 2. Actualizar productos (M2M)
        grupo.productos.set(productos)

        # 3. Upsert de opciones (estrategia segura)
        ids_en_payload = set()
        for op_data in opciones_payload:
            nombre = op_data.get("nombre", "").strip()
            precio = op_data.get("precio_extra", 0)
            op_id  = op_data.get("id")

            if op_id:
                # Actualizar existente si pertenece al grupo
                OpcionModificador.objects.filter(pk=op_id, grupo=grupo).update(
                    nombre_opcion=nombre,
                    precio_extra=precio,
                )
                ids_en_payload.add(int(op_id))
            else:
                # Crear nueva opción
                nueva = OpcionModificador.objects.create(
                    nombre_opcion=nombre,
                    precio_extra=precio,
                    grupo=grupo,
                )
                ids_en_payload.add(nueva.pk)

        # 4. Opciones que ya no están en el payload:
        #    - Si no tienen usos → eliminar físicamente (limpia el catálogo)
        #    - Si tienen usos (ProtectedError) → soft-delete: activo=False
        opciones_a_eliminar = grupo.opciones.exclude(pk__in=ids_en_payload)
        for op in opciones_a_eliminar:
            try:
                op.delete()
            except ProtectedError:
                # Tiene usos en DetalleModificador → marcar inactiva para preservar histórico
                op.activo = False
                op.save(update_fields=["activo"])

    return JsonResponse({"ok": True, "grupo_id": grupo.pk})


# ─── Promociones ──────────────────────────────────────────────────────────────

@gerente_requerido
def promociones(request):
    if request.method == "POST":
        titulo = request.POST.get("titulo", "").strip()
        tipo_descuento_id = request.POST.get("tipo_descuento_id")
        valor_descuento = request.POST.get("valor_descuento") or None
        cantidad_minima = request.POST.get("cantidad_minima") or None
        aplicacion = request.POST.get("aplicacion", "item")
        fecha_inicio = request.POST.get("fecha_inicio")
        fecha_fin = request.POST.get("fecha_fin")

        if not (titulo and tipo_descuento_id and fecha_inicio and fecha_fin):
            messages.error(request, "Faltan campos obligatorios.")
            return redirect("gerente:promociones")

        tipo = get_object_or_404(TipoDescuento, pk=tipo_descuento_id)

        # Convertir valores numéricos correctamente
        valor_decimal = Decimal(valor_descuento) if valor_descuento else None
        cantidad_int = int(cantidad_minima) if cantidad_minima else None

        imagen_url_promo = request.POST.get("imagen_url", "").strip() or None
        promocion = Promocion.objects.create(
            titulo=titulo,
            tipo_descuento=tipo,
            valor_descuento=valor_decimal,
            cantidad_minima=cantidad_int,
            aplicacion=aplicacion,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            activa=True,
            imagen_url=imagen_url_promo,
        )

        ids_aplicables = request.POST.getlist("productos_aplicables")
        ids_beneficiados = request.POST.getlist("productos_beneficiados")
        if ids_aplicables:
            promocion.productos_aplicables.set(ids_aplicables)
        if ids_beneficiados:
            promocion.productos_beneficiados.set(ids_beneficiados)

        messages.success(request, f"Promoción '{titulo}' creada exitosamente.")
        return redirect("gerente:promociones")

    # GET
    promos = Promocion.objects.select_related("tipo_descuento").prefetch_related(
        "productos_aplicables"
    ).order_by("-fecha_inicio")
    tipos_descuento = TipoDescuento.objects.all()
    productos_list = Producto.objects.filter(disponible=True).order_by("nombre")
    return render(request, "gerente/menu_manager.html", {
        "promociones": promos,
        "tipos_descuento": tipos_descuento,
        "productos_list": productos_list,
        "vista": "promociones",
    })


@require_POST
@gerente_requerido
def promocion_toggle(request, id):
    promo = get_object_or_404(Promocion, pk=id)
    promo.activa = not promo.activa
    promo.save(update_fields=["activa"])
    return JsonResponse({"ok": True, "activa": promo.activa})


@require_POST
@gerente_requerido
def promocion_eliminar(request, id):
    promo = get_object_or_404(Promocion, pk=id)
    promo.delete()
    return JsonResponse({"ok": True})


@gerente_requerido
def promocion_editar(request, id):
    promo = get_object_or_404(Promocion, pk=id)

    if request.method == "POST":
        titulo = request.POST.get("titulo", "").strip()
        tipo_descuento_id = request.POST.get("tipo_descuento_id")
        valor_descuento = request.POST.get("valor_descuento") or None
        cantidad_minima = request.POST.get("cantidad_minima") or None
        aplicacion = request.POST.get("aplicacion", "item")
        fecha_inicio = request.POST.get("fecha_inicio")
        fecha_fin = request.POST.get("fecha_fin")

        if not (titulo and tipo_descuento_id and fecha_inicio and fecha_fin):
            messages.error(request, "Faltan campos obligatorios.")
            return redirect("gerente:promociones")

        tipo = get_object_or_404(TipoDescuento, pk=tipo_descuento_id)
        promo.titulo = titulo
        promo.tipo_descuento = tipo
        promo.valor_descuento = Decimal(valor_descuento) if valor_descuento else None
        promo.cantidad_minima = int(cantidad_minima) if cantidad_minima else None
        promo.aplicacion = aplicacion
        promo.fecha_inicio = fecha_inicio
        promo.fecha_fin = fecha_fin
        promo.imagen_url = request.POST.get("imagen_url", "").strip() or None
        promo.save()

        ids_aplicables = request.POST.getlist("productos_aplicables")
        ids_beneficiados = request.POST.getlist("productos_beneficiados")
        if ids_aplicables:
            promo.productos_aplicables.set(ids_aplicables)
        else:
            promo.productos_aplicables.clear()
        if ids_beneficiados:
            promo.productos_beneficiados.set(ids_beneficiados)
        else:
            promo.productos_beneficiados.clear()

        messages.success(request, f"Promoción '{titulo}' actualizada.")
        return redirect("gerente:promociones")

    # GET: devolver JSON con los datos de la promo para cargar en el modal
    data = {
        "id": promo.pk,
        "titulo": promo.titulo,
        "tipo_descuento_id": promo.tipo_descuento_id,
        "aplicacion": promo.aplicacion,
        "valor_descuento": str(promo.valor_descuento) if promo.valor_descuento else "",
        "cantidad_minima": promo.cantidad_minima or "",
        "fecha_inicio": promo.fecha_inicio.strftime("%Y-%m-%dT%H:%M"),
        "fecha_fin": promo.fecha_fin.strftime("%Y-%m-%dT%H:%M"),
        "productos_aplicables": list(promo.productos_aplicables.values_list("id", flat=True)),
        "productos_beneficiados": list(promo.productos_beneficiados.values_list("id", flat=True)),
        "activa": promo.activa,
        "imagen_url": promo.imagen_url or "",
    }
    return JsonResponse(data)


# ─── Empleados ────────────────────────────────────────────────────────────────

@gerente_requerido
def empleados(request):
    activos = Empleado.objects.filter(activo=True).order_by("-pk")
    inactivos = Empleado.objects.filter(activo=False).order_by("-pk")
    return render(request, "gerente/empleados.html", {
        "activos": activos, "inactivos": inactivos
    })


@require_POST
@gerente_requerido
def empleados_nuevo(request):
    nombre = request.POST.get("nombre", "").strip()
    usuario = request.POST.get("usuario", "").strip()
    password = request.POST.get("password", "")
    rol = request.POST.get("rol", "mesero")
    if nombre and usuario and password:
        Empleado.objects.create_user(
            username=usuario, password=password, nombre=nombre, rol=rol
        )
    return redirect("gerente:empleados")


@require_POST
@gerente_requerido
def empleado_toggle(request, id):
    """Activa o desactiva un empleado."""
    emp = get_object_or_404(Empleado, pk=id)
    emp.activo = not emp.activo
    emp.is_active = emp.activo
    emp.save(update_fields=["activo", "is_active"])
    return JsonResponse({"ok": True, "activo": emp.activo})


@require_POST
@gerente_requerido
def empleado_editar(request, id):
    emp = get_object_or_404(Empleado, pk=id)
    nombre = request.POST.get("nombre", emp.nombre).strip()
    rol = request.POST.get("rol", emp.rol)
    password = request.POST.get("password", "").strip()
    emp.nombre = nombre
    emp.rol = rol
    if password:
        emp.set_password(password)
    emp.save()
    return redirect("gerente:empleados")


# ─── Reportes ─────────────────────────────────────────────────────────────────

@gerente_requerido
def reportes(request):
    periodo = request.GET.get("periodo", "semana")
    hoy = timezone.now().date()
    if periodo == "hoy":
        desde = hoy
    elif periodo == "mes":
        desde = hoy - timedelta(days=30)
    else:
        desde = hoy - timedelta(days=7)

    base_qs = Pedido.objects.filter(fecha_hora_ingreso__date__gte=desde)

    # BUG #6 FIX: cancelaciones se obtienen de un queryset independiente.
    # Antes se excluían los cancelados al inicio y luego se filtraba sobre el
    # mismo queryset buscando cancelados, obteniendo siempre una lista vacía.
    pedidos = base_qs.exclude(estado="cancelado").prefetch_related(
        "detalles__producto"
    ).select_related("sesion__mesa").order_by("-fecha_hora_ingreso")

    cancelaciones = base_qs.filter(estado="cancelado").select_related("sesion__mesa")

    # KPIs — usar agregación BD en lugar de Python loop (más eficiente y preciso)
    from django.db.models.functions import Coalesce as _Coalesce
    agg    = pedidos.aggregate(t=_Coalesce(Sum("detalles__subtotal_calculado"), Decimal("0.00")))
    total  = agg["t"]                                          # Decimal
    tickets = pedidos.count()
    ticket_promedio = (total / tickets).quantize(Decimal("0.01")) if tickets else Decimal("0.00")

    # Ventas por día — Coalesce garantiza 0 en días sin ventas (evita None en JSON)
    ventas_por_dia_qs = pedidos.annotate(
        fecha=TruncDate("fecha_hora_ingreso")
    ).values("fecha").annotate(
        total=Coalesce(
            Sum("detalles__subtotal_calculado"),
            Decimal("0.00"),
            output_field=DecimalField()
        ),
        tickets=Count("id", distinct=True),
    ).order_by("fecha")

    ventas_por_dia = []
    for row in ventas_por_dia_qs:
        fecha = row.get("fecha") if isinstance(row, dict) else row["fecha"]
        if fecha is None:
            logger.warning("ventas_por_dia: fila con fecha=None ignorada — posible dato corrupto: %r", row)
            continue
        ventas_por_dia.append({
            "dia":     fecha.strftime("%a %d/%m"),
            "total":   float(row["total"]),   # solo float al serializar a JSON
            "tickets": row["tickets"],
        })

    # Productos más vendidos
    top_productos = DetallePedido.objects.filter(
        pedido__fecha_hora_ingreso__date__gte=desde
    ).exclude(pedido__estado="cancelado").values("producto__nombre").annotate(
        total_vendido=Sum("cantidad"),
        ingreso=Sum("subtotal_calculado")
    ).order_by("-total_vendido")[:10]

    return render(request, "gerente/reportes.html", {
        "pedidos": pedidos, "total": total, "periodo": periodo,
        "tickets": tickets, "ticket_promedio": round(ticket_promedio, 2),
        "ventas_por_dia": json.dumps(ventas_por_dia),
        "top_productos": list(top_productos),
        "cancelaciones": cancelaciones,
        "desde": desde,
        "hasta": hoy,
    })


# ─── Exportación de reportes ──────────────────────────────────────────────────

@gerente_requerido
def reporte_exportar(request):
    """GET ?formato=excel|pdf&desde=YYYY-MM-DD&hasta=YYYY-MM-DD"""
    from apps.gerente.reports import exportar_excel, exportar_pdf
    from datetime import date as date_type
    from django.contrib import messages

    fmt = request.GET.get("formato", "excel")
    hoy = timezone.now().date()

    try:
        desde = date_type.fromisoformat(request.GET.get("desde", str(hoy - timedelta(days=7))))
        hasta = date_type.fromisoformat(request.GET.get("hasta", str(hoy)))
    except ValueError:
        messages.error(request, "Fechas inválidas para el reporte.")
        return redirect("gerente:reportes")

    if fmt == "pdf":
        try:
            pdf_bytes = exportar_pdf(desde, hasta)
        except ImportError:
            messages.error(request, "WeasyPrint no está instalado. Ejecuta: pip install weasyprint==62.3 (y reconstruye el contenedor Docker con las dependencias del Dockerfile).")
            return redirect("gerente:reportes")
        except Exception as e:
            messages.error(request, f"Error al generar el PDF: {e}")
            return redirect("gerente:reportes")
        from django.http import HttpResponse
        filename = f"reporte-mochi-{desde}-{hasta}.pdf"
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    # Default: Excel
    try:
        xlsx_bytes = exportar_excel(desde, hasta)
    except ImportError:
        messages.error(request, "openpyxl no está instalado. Ejecuta: pip install openpyxl==3.1.2")
        return redirect("gerente:reportes")
    except Exception as e:
        messages.error(request, f"Error al generar el Excel: {e}")
        return redirect("gerente:reportes")
    from django.http import HttpResponse
    filename = f"reporte-mochi-{desde}-{hasta}.xlsx"
    resp = HttpResponse(
        xlsx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@gerente_requerido
def reportes_quincenales(request):
    """Lista los reportes quincenales generados disponibles para descarga."""
    from pathlib import Path
    from django.conf import settings as django_settings

    media_root = Path(getattr(django_settings, "MEDIA_ROOT", "media"))
    reportes_dir = media_root / "reportes"
    archivos = []
    if reportes_dir.exists():
        for f in sorted(reportes_dir.iterdir(), reverse=True):
            if f.suffix in (".xlsx", ".pdf") and f.name.startswith("reporte_quincenal_"):
                archivos.append({
                    "nombre": f.name,
                    "url": f"/media/reportes/{f.name}",
                    "tipo": "Excel" if f.suffix == ".xlsx" else "PDF",
                    "icono": "bi-file-earmark-excel" if f.suffix == ".xlsx" else "bi-file-earmark-pdf",
                    "color": "#1D6F42" if f.suffix == ".xlsx" else "#C0392B",
                    "tamaño": f"{f.stat().st_size // 1024} KB",
                })
    return render(request, "gerente/reportes.html", {
        "archivos_quincenales": archivos,
        "vista": "quincenales",
        "desde": timezone.now().date() - timedelta(days=30),
        "hasta": timezone.now().date(),
    })


# ─── Auditoría ────────────────────────────────────────────────────────────────

@gerente_requerido
def auditoria(request):
    registros = Auditoria.objects.select_related("empleado", "mesa", "pedido").order_by("-fecha_hora")[:200]
    return render(request, "gerente/reportes.html", {
        "registros": registros, "vista": "auditoria"
    })


# ─── Configuración ────────────────────────────────────────────────────────────

@gerente_requerido
def configuracion(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, Exception):
            data = request.POST
        yellow = data.get("yellow")
        red = data.get("red")
        mantenimiento = data.get("modo_mantenimiento")
        mensaje_mant = data.get("mensaje_mantenimiento")
        if yellow is not None:
            Configuracion.objects.update_or_create(
                clave="semaforo_yellow", defaults={"valor": str(yellow)}
            )
        if red is not None:
            Configuracion.objects.update_or_create(
                clave="semaforo_red", defaults={"valor": str(red)}
            )
        if mantenimiento is not None:
            Configuracion.objects.update_or_create(
                clave="modo_mantenimiento",
                defaults={"valor": "true" if str(mantenimiento).lower() in ("true", "1", "yes") else "false"}
            )
        if mensaje_mant is not None:
            Configuracion.objects.update_or_create(
                clave="mensaje_mantenimiento", defaults={"valor": str(mensaje_mant)}
            )
        return JsonResponse({"ok": True})

    listos_count = Pedido.objects.filter(estado="listo").count()
    yellow_cfg = Configuracion.objects.filter(clave="semaforo_yellow").first()
    red_cfg = Configuracion.objects.filter(clave="semaforo_red").first()
    mant_cfg = Configuracion.objects.filter(clave="modo_mantenimiento").first()
    msg_cfg = Configuracion.objects.filter(clave="mensaje_mantenimiento").first()
    return render(request, "gerente/configuracion.html", {
        "listos_count": listos_count,
        "semaforo_yellow": int(yellow_cfg.valor) if yellow_cfg else 8,
        "semaforo_red": int(red_cfg.valor) if red_cfg else 15,
        "modo_mantenimiento": mant_cfg.valor.lower() in ("true", "1") if mant_cfg else False,
        "mensaje_mantenimiento": msg_cfg.valor if msg_cfg else "",
    })