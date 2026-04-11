"""
gerente/views.py — Con cancelar_pedido, toggle_empleado y reportes enriquecidos.
"""
import json
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from datetime import timedelta

from accounts.decorators import gerente_requerido
from accounts.models import Empleado
from menu.models import Categoria, Producto, GrupoModificador, OpcionModificador, Promocion, TipoPromocion
from mesas.models import Mesa, SesionCliente
from pedidos.models import Pedido, DetallePedido, SolicitudPago
from auditoria.models import Auditoria
from catalogs.models import MetodoPago, EstadoSolicitud


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
    pedidos_hoy = Pedido.objects.filter(fecha_hora_ingreso__date=hoy)
    ventas_hoy = float(sum(
        sum(d.subtotal_calculado for d in p.detalles.all())
        for p in pedidos_hoy.prefetch_related("detalles")
    ))
    return JsonResponse({
        "ventas_hoy": ventas_hoy,
        "pedidos_hoy": pedidos_hoy.count(),
        "mesas_ocupadas": Mesa.objects.filter(estado="ocupada").count(),
        "listos_count": Pedido.objects.filter(estado="listo").count(),
        "solicitudes_count": SolicitudPago.objects.filter(
            estado_solicitud__descripcion="pendiente"
        ).count(),
    })


# ─── Detalle de mesa (reutiliza lógica de mesero) ────────────────────────────

@require_GET
@gerente_requerido
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

    # Registrar en auditoría
    Auditoria.objects.create(
        accion="Pedido cancelado",
        detalle=f"Pedido #{pedido.pk} cancelado. Motivo: {motivo}",
        empleado=request.user,
        mesa=pedido.sesion.mesa,
        pedido=pedido,
    )

    return JsonResponse({"ok": True})


# ─── Mesas ────────────────────────────────────────────────────────────────────

@gerente_requerido
def mesas_estado(request):
    """JSON polling para el floor plan del gerente."""
    mesas = Mesa.objects.prefetch_related("sesiones__pedidos").order_by("numero_mesa")
    listos_count = Pedido.objects.filter(estado="listo").count()
    solicitudes_count = SolicitudPago.objects.filter(
        estado_solicitud__descripcion="pendiente"
    ).count()
    data = []
    for m in mesas:
        sesiones_activas = m.sesiones.filter(estado="activa")
        pedidos_cocina = 0
        pedidos_listos = 0
        tiene_solicitud = False
        for s in sesiones_activas:
            pedidos_cocina += s.pedidos.filter(estado__in=["recibido", "preparando"]).count()
            pedidos_listos += s.pedidos.filter(estado="listo").count()
            if s.solicitudes_pago.filter(estado_solicitud__descripcion="pendiente").exists():
                tiene_solicitud = True

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
            "clientes": sesiones_activas.count(),
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
        ubicacion = request.POST.get("ubicacion", "").strip()
        import uuid as _uuid
        qr = f"mesa-{numero}-{_uuid.uuid4().hex[:8]}"
        Mesa.objects.get_or_create(
            numero_mesa=numero,
            defaults={"capacidad": capacidad, "ubicacion": ubicacion or None, "codigo_qr": qr}
        )
        return redirect("gerente:mesas_crud")

    all_mesas = Mesa.objects.order_by("numero_mesa")
    meseros = Empleado.objects.filter(rol="mesero", activo=True)
    return render(request, "gerente/menu_manager.html", {
        "mesas": all_mesas, "meseros": meseros, "vista": "mesas"
    })


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
    grupos = GrupoModificador.objects.select_related("producto").prefetch_related("opciones").order_by("producto__nombre")
    productos_list = Producto.objects.filter(disponible=True).order_by("nombre")
    return render(request, "gerente/menu_manager.html", {
        "grupos": grupos, "productos_list": productos_list, "vista": "modificadores"
    })


@require_POST
@gerente_requerido
def modificador_crear(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False}, status=400)
    producto = get_object_or_404(Producto, pk=data.get("producto_id"))
    grupo = GrupoModificador.objects.create(
        nombre_grupo=data.get("nombre_grupo", "").strip(),
        tipo=data.get("tipo", "única"),
        es_obligatorio=data.get("es_obligatorio", False),
        max_selecciones=data.get("max_selecciones") or None,
        producto=producto,
    )
    for op in data.get("opciones", []):
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


# ─── Promociones ──────────────────────────────────────────────────────────────

@gerente_requerido
def promociones(request):
    promos = Promocion.objects.select_related("tipo_promocion").order_by("-fecha_inicio")
    tipos = TipoPromocion.objects.all()
    productos_list = Producto.objects.filter(disponible=True).order_by("nombre")
    return render(request, "gerente/menu_manager.html", {
        "promociones": promos, "tipos": tipos,
        "productos_list": productos_list, "vista": "promociones"
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


# ─── Empleados ────────────────────────────────────────────────────────────────

@gerente_requerido
def empleados(request):
    activos = Empleado.objects.filter(activo=True).order_by("nombre")
    inactivos = Empleado.objects.filter(activo=False).order_by("nombre")
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

    pedidos = Pedido.objects.filter(
        fecha_hora_ingreso__date__gte=desde
    ).prefetch_related("detalles__producto").select_related("sesion__mesa").order_by("-fecha_hora_ingreso")

    # KPIs
    total = sum(sum(d.subtotal_calculado for d in p.detalles.all()) for p in pedidos)
    tickets = pedidos.count()
    ticket_promedio = float(total / tickets) if tickets else 0

    # Ventas por día (últimos 7 o 30 días)
    dias = (hoy - desde).days + 1
    ventas_por_dia = []
    for i in range(dias):
        dia = desde + timedelta(days=i)
        ps = [p for p in pedidos if p.fecha_hora_ingreso.date() == dia]
        total_dia = sum(sum(d.subtotal_calculado for d in p.detalles.all()) for p in ps)
        ventas_por_dia.append({"dia": dia.strftime("%a"), "total": float(total_dia), "tickets": len(ps)})

    # Productos más vendidos
    from django.db.models import Sum, Count
    top_productos = DetallePedido.objects.filter(
        pedido__fecha_hora_ingreso__date__gte=desde
    ).values("producto__nombre").annotate(
        total_vendido=Sum("cantidad"),
        ingreso=Sum("subtotal_calculado")
    ).order_by("-total_vendido")[:10]

    # Cancelaciones
    cancelaciones = pedidos.filter(estado="cancelado").select_related("sesion__mesa")

    return render(request, "gerente/reportes.html", {
        "pedidos": pedidos, "total": total, "periodo": periodo,
        "tickets": tickets, "ticket_promedio": round(ticket_promedio, 2),
        "ventas_por_dia": json.dumps(ventas_por_dia),
        "top_productos": list(top_productos),
        "cancelaciones": cancelaciones,
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
        # Guardar configuración (simplificado — en producción usar un modelo Config)
        return JsonResponse({"ok": True})
    return render(request, "gerente/configuracion.html")
