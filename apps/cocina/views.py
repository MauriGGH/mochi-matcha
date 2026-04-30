"""
cocina/views.py — KDS con filtrado por área (cocina / bar).
"""
import json
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone

from apps.accounts.decorators import cocina_requerido
from apps.pedidos.models import Pedido
from apps.gerente.models import Configuracion


def login_cocina(request):
    if request.user.is_authenticated and request.user.rol in ("cocina", "gerente", "admin"):
        return redirect("cocina:kds")
    error = None
    if request.method == "POST":
        usuario = request.POST.get("usuario", "")
        contrasena = request.POST.get("contrasena", "")
        user = authenticate(request, username=usuario, password=contrasena)
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
    logout(request)
    return redirect("cocina:login_cocina")


def _filtrar_pedidos_por_area(pedidos_qs, area):
    """
    Filtra los pedidos según el área de la categoría del producto.
    area: 'cocina' | 'bar'
    """
    if area == "bar":
        return pedidos_qs.filter(
            detalles__producto__categoria__area__in=["bar", "ambos"]
        ).distinct()
    elif area == "cocina":
        return pedidos_qs.filter(
            detalles__producto__categoria__area__in=["cocina", "ambos"]
        ).distinct()
    return pedidos_qs


@cocina_requerido
def kds(request):
    area = request.GET.get("area", "cocina")  # cocina | bar
    qs = Pedido.objects.filter(
        estado__in=["recibido", "preparando"]
    ).prefetch_related(
        "detalles__producto__categoria",
        "detalles__modificadores__opcion",
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")

    pedidos = _filtrar_pedidos_por_area(qs, area)

    # Annotate each pedido with only the detalles relevant to this area
    for pedido in pedidos:
        pedido.detalles_filtrados = [
            d for d in pedido.detalles.all()
            if d.producto.categoria.area in (area, "ambos")
        ]

    # Pedidos listos para entrega (panel derecho)
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
    area = request.GET.get("area", "cocina")
    qs = Pedido.objects.filter(
        estado__in=["recibido", "preparando"]
    ).prefetch_related(
        "detalles__producto__categoria",
        "detalles__modificadores__opcion",
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")

    pedidos = _filtrar_pedidos_por_area(qs, area)

    # Listos también para actualizar el panel derecho
    qs_listos = Pedido.objects.filter(estado="listo").prefetch_related(
        "detalles__producto__categoria"
    ).select_related("sesion__mesa").order_by("fecha_hora_ingreso")
    listos = _filtrar_pedidos_por_area(qs_listos, area)

    def serializar(p, area_filter):
        return {
            "id": p.pk,
            "estado": p.estado,
            "mesa": p.sesion.mesa.numero_mesa,
            "alias": p.sesion.alias,
            "fecha": p.fecha_hora_ingreso.isoformat(),
            "detalles_filtrados": [
                {
                    "nombre": d.producto.nombre,
                    "cantidad": d.cantidad,
                    "notas": d.notas or "",
                    "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
                }
                for d in p.detalles.all()
                if d.producto.categoria.area in (area_filter, "ambos")
            ],
            # legacy alias kept for backward compat with old buildCard
            "items": [
                {
                    "nombre": d.producto.nombre,
                    "cantidad": d.cantidad,
                    "notas": d.notas or "",
                    "modificadores": [m.opcion.nombre_opcion for m in d.modificadores.all()],
                }
                for d in p.detalles.all()
                if d.producto.categoria.area in (area_filter, "ambos")
            ],
        }

    return JsonResponse({
        "ok": True,
        "ts": int(timezone.now().timestamp() * 1000),
        "pendientes": [serializar(p, area) for p in pedidos],
        "listos": [serializar(p, area) for p in listos],
    })


@require_POST
@cocina_requerido
def marcar_listo(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False}, status=400)
    pedido = get_object_or_404(Pedido, pk=data.get("pedido_id"))
    if pedido.estado == "recibido":
        pedido.estado = "preparando"
    elif pedido.estado == "preparando":
        pedido.estado = "listo"
    pedido.save(update_fields=["estado"])
    return JsonResponse({"ok": True, "nuevo_estado": pedido.estado})
