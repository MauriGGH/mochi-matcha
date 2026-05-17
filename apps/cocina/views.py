"""
cocina/views.py — KDS con filtrado por área (cocina / bar).

Estado de preparación POR ÁREA
------------------------------
Un pedido puede mezclar productos de cocina y de bar. Cada DetallePedido tiene
su propio flag `listo`. El KDS de un área marca como listos SOLO los ítems de
esa área; el `Pedido.estado` global pasa a "listo" únicamente cuando TODOS los
detalles están listos. Así, un pedido permanece "preparando" hasta que ambas
áreas terminan.
"""
import json
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.db import transaction

from apps.accounts.decorators import cocina_requerido
from apps.pedidos.models import Pedido
from apps.gerente.models import Configuracion


@never_cache
@ensure_csrf_cookie
def login_cocina(request):
    """
    Login exclusivo para el módulo de cocina/KDS.

    Solo acceden los roles 'cocina', 'gerente' y 'admin'. Si el usuario ya está
    autenticado con uno de esos roles, se redirige directamente al KDS.
    @never_cache evita que el navegador muestre el formulario tras el login.
    @ensure_csrf_cookie garantiza que la cookie CSRF esté presente para el POST.
    """
    if request.user.is_authenticated and request.user.rol in ("cocina", "gerente", "admin"):
        return redirect("cocina:kds")
    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, usuario=usuario, password=contrasena)
        if user and user.rol in ("cocina", "gerente", "admin") and user.is_active:
            login(request, user)
            return redirect("cocina:kds")
        error = "Credenciales incorrectas o sin acceso a este módulo."
    return render(request, "base/login.html", {
        "rol": "cocina", "rol_display": "Cocina",
        "form_action": "/cocina/login/", "error": error,
        "usuario_previo": request.POST.get("usuario", ""),
    })


def logout_cocina(request):
    """Cierra la sesión del personal de cocina y redirige al login del módulo."""
    logout(request)
    return redirect("cocina:login_cocina")


def _areas_de(area):
    """Categorías que le competen al KDS de un área (incluye 'ambos')."""
    if area == "bar":
        return ["bar", "ambos"]
    if area == "cocina":
        return ["cocina", "ambos"]
    return ["cocina", "bar", "ambos"]


def _detalle_es_de_area(detalle, area):
    return detalle.producto.categoria.area in _areas_de(area)


def _filtrar_pedidos_por_area(pedidos_qs, area):
    """Pedidos que tienen al menos un ítem de esta área (sin importar si está listo)."""
    return pedidos_qs.filter(
        detalles__producto__categoria__area__in=_areas_de(area)
    ).distinct()


def _filtrar_pendientes_por_area(pedidos_qs, area):
    """
    Pedidos PENDIENTES para esta área: tienen al menos un ítem de esta área que
    TODAVÍA NO está listo. Si el área ya terminó todos sus ítems, el pedido
    desaparece de su columna aunque otra área siga trabajando.
    """
    return pedidos_qs.filter(
        detalles__producto__categoria__area__in=_areas_de(area),
        detalles__listo=False,
    ).distinct()


@cocina_requerido
def kds(request):
    """
    Vista principal del KDS (Kitchen Display System).

    Recibe el parámetro GET 'area' (cocina | bar) para mostrar únicamente los
    ítems que le corresponden a esa área de preparación. Inyecta en el contexto:
      - pedidos: pendientes con ítems de esta área sin marcar listos.
      - pedidos_listos: pedidos cuyo estado global ya es "listo" (lista de entrega).
      - semaforo_yellow / semaforo_red: umbrales de tiempo (min) leídos desde BD.
    Los umbrales del semáforo se leen desde la tabla Configuracion para que el
    gerente pueda ajustarlos sin redeploy.
    """
    area = request.GET.get("area", "cocina")  # cocina | bar
    qs = Pedido.objects.filter(
        estado__in=["recibido", "preparando"]
    ).prefetch_related(
        "detalles__producto__categoria",
        "detalles__modificadores__opcion",
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")

    # Pendientes: solo pedidos con ítems de esta área aún no listos.
    pedidos = _filtrar_pendientes_por_area(qs, area)

    # Anotar cada pedido con los detalles de esta área (con su flag `listo`).
    for pedido in pedidos:
        pedido.detalles_filtrados = [
            d for d in pedido.detalles.all() if _detalle_es_de_area(d, area)
        ]

    # Pedidos listos para entrega (panel derecho): estado global "listo".
    qs_listos = Pedido.objects.filter(
        estado="listo"
    ).prefetch_related(
        "detalles__producto__categoria"
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")
    pedidos_listos = _filtrar_pedidos_por_area(qs_listos, area)

    return render(request, "cocina/kds.html", {
        "pedidos": pedidos,
        "pedidos_listos": pedidos_listos,
        "area": area,
        "pendientes_count": pedidos.count(),
        "listos_count": pedidos_listos.count(),
        "semaforo_yellow": int(Configuracion.objects.filter(clave="semaforo_yellow").values_list("valor", flat=True).first() or 8),
        "semaforo_red": int(Configuracion.objects.filter(clave="semaforo_red").values_list("valor", flat=True).first() or 15),
    })


@require_GET
@cocina_requerido
def pedidos_json(request):
    """
    Endpoint de polling del KDS. Devuelve JSON con el estado actualizado de:
      - pendientes: pedidos con ítems de esta área sin terminar.
      - listos: pedidos con estado global "listo" visibles para esta área.
      - ts: timestamp del servidor en milisegundos (usado por el cliente para
            descartar respuestas tardías desordenadas).
    Solo acepta GET. Requiere rol cocina/gerente/admin.
    """
    area = request.GET.get("area", "cocina")
    qs = Pedido.objects.filter(
        estado__in=["recibido", "preparando"]
    ).prefetch_related(
        "detalles__producto__categoria",
        "detalles__modificadores__opcion",
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")

    pedidos = _filtrar_pendientes_por_area(qs, area)

    # Listos también para actualizar el panel derecho.
    # Se muestran todos los pedidos con estado "listo" que tengan ítems del área
    # actual, pero el contenido serializado incluye TODOS los ítems del pedido
    # para que el mesero vea el pedido completo al entregar.
    qs_listos = Pedido.objects.filter(estado="listo").prefetch_related(
        "detalles__producto__categoria",
        "detalles__modificadores__opcion",
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")
    listos = _filtrar_pedidos_por_area(qs_listos, area)

    def serializar_pendiente(p, area_filter):
        detalles_area = [
            d for d in p.detalles.all() if _detalle_es_de_area(d, area_filter)
        ]
        items = [
            {
                "nombre": d.producto.nombre,
                "cantidad": d.cantidad,
                "notas": d.notas or "",
                "listo": d.listo,
                "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
            }
            for d in detalles_area
        ]
        return {
            "id": p.pk,
            "estado": p.estado,
            "mesa": p.sesion.mesa.numero_mesa,
            "alias": p.sesion.alias,
            "fecha": p.fecha_hora_ingreso.isoformat(),
            "area_completa": all(d.listo for d in detalles_area) if detalles_area else True,
            "detalles_filtrados": items,
            "items": items,
        }

    def serializar_listo(p):
        # Para pedidos listos se muestran TODOS los ítems (todas las áreas)
        # para que el mesero vea el pedido completo al momento de entregarlo.
        todos_detalles = list(p.detalles.all())
        items = [
            {
                "nombre": d.producto.nombre,
                "cantidad": d.cantidad,
                "notas": d.notas or "",
                "listo": d.listo,
                "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
            }
            for d in todos_detalles
        ]
        return {
            "id": p.pk,
            "estado": p.estado,
            "mesa": p.sesion.mesa.numero_mesa,
            "alias": p.sesion.alias,
            "fecha": p.fecha_hora_ingreso.isoformat(),
            "area_completa": True,
            "detalles_filtrados": items,
            "items": items,
        }

    return JsonResponse({
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "pendientes": [serializar_pendiente(p, area) for p in pedidos],
        "listos": [serializar_listo(p) for p in listos],
    })


@require_POST
@cocina_requerido
def marcar_listo(request):
    """
    Avanza un pedido en el KDS para un ÁREA concreta:
      - estado "recibido"  → "preparando" (alguien comenzó; no marca ítems).
      - estado "preparando" → marca como listos los ítems de ESA área.
        El pedido global pasa a "listo" SOLO cuando todos los ítems lo están.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False}, status=400)

    area = data.get("area", "cocina")
    if area not in ("cocina", "bar"):
        area = "cocina"

    with transaction.atomic():
        pedido = (
            Pedido.objects
            .select_for_update()
            .filter(pk=data.get("pedido_id"))
            .first()
        )
        if pedido is None:
            return JsonResponse({"ok": False, "error": "Pedido no encontrado."}, status=404)

        if pedido.estado not in ("recibido", "preparando"):
            # Ya está listo/entregado/cancelado: nada que hacer.
            return JsonResponse({
                "ok": True, "nuevo_estado": pedido.estado, "area_completa": True,
            })

        detalles = list(pedido.detalles.select_related("producto__categoria"))
        detalles_area = [d for d in detalles if _detalle_es_de_area(d, area)]

        if pedido.estado == "recibido":
            # Primer clic: solo arranca la preparación del pedido.
            pedido.estado = "preparando"
            pedido.save(update_fields=["estado"])
            return JsonResponse({
                "ok": True,
                "nuevo_estado": "preparando",
                "area_completa": all(d.listo for d in detalles_area) if detalles_area else True,
            })

        # estado == "preparando": marcar como listos los ítems de esta área.
        ahora = timezone.now()
        for d in detalles_area:
            if not d.listo:
                d.listo = True
                d.fecha_listo = ahora
                d.save(update_fields=["listo", "fecha_listo"])

        # BUGFIX (problema 2): el pedido global solo pasa a "listo" cuando TODOS
        # sus detalles (todas las áreas) están listos. Si falta alguno, queda
        # en "preparando" y el cliente lo sigue viendo en preparación.
        todos_listos = all(d.listo for d in detalles)
        nuevo_estado = "listo" if todos_listos else "preparando"
        if pedido.estado != nuevo_estado:
            pedido.estado = nuevo_estado
            pedido.save(update_fields=["estado"])

        return JsonResponse({
            "ok": True,
            "nuevo_estado": nuevo_estado,
            "area_completa": True,   # esta área ya terminó sus ítems
        })
