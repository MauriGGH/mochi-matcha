"""
apps/pedidos/utils.py
Lógica centralizada de aplicación de promociones al carrito de compras.

Uso:
    from apps.pedidos.utils import aplicar_promociones
    carrito, aplicadas = aplicar_promociones(items, sesion_cliente)
"""
from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

from django.utils import timezone


# ─── Tipos de descuento canónicos (deben coincidir con TipoDescuento.descripcion) ─
TD_PORCENTAJE = "Porcentaje"
TD_MONTO_FIJO = "Monto fijo"
TD_2X1 = "2x1"
TD_COMBO = "Combo precio fijo"
TD_LLEVA_X = "Lleva X paga Y"


def _aplicar_una(carrito, promo, ids_aplicables, aplicadas):
    """Aplica una promoción concreta al carrito (in-place)."""
    tipo = promo.tipo_descuento.descripcion
    if tipo == TD_PORCENTAJE:
        _aplicar_porcentaje(carrito, promo, ids_aplicables, aplicadas)
    elif tipo == TD_MONTO_FIJO:
        if promo.aplicacion == "total":
            _aplicar_monto_total(carrito, promo, aplicadas)
        else:
            _aplicar_monto_por_item(carrito, promo, ids_aplicables, aplicadas)
    elif tipo == TD_2X1:
        _aplicar_2x1(carrito, promo, ids_aplicables, aplicadas)
    elif tipo == TD_LLEVA_X:
        _aplicar_lleva_x_paga_y(carrito, promo, ids_aplicables, aplicadas)
    elif tipo == TD_COMBO:
        ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
        _aplicar_combo(carrito, promo, ids_aplicables, ids_beneficiados, aplicadas)


def _promo_es_elegible(promo, carrito_items):
    """¿Hay al menos un ítem del carrito que sea aplicable a esta promo?"""
    if promo.tipo_descuento is None:
        return False
    ids_aplicables = set(promo.productos_aplicables.values_list("id", flat=True))
    ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
    ids_carrito = {int(it["producto_id"]) for it in carrito_items}

    # Promos sobre total: aplica si hay cualquier ítem
    if promo.aplicacion == "total":
        return bool(ids_carrito)

    # Promos con dos grupos distintos (aplicables = condición disparadora,
    # beneficiados = productos con descuento): exige ≥1 de cada grupo en carrito.
    # Ejemplo: "MATCHA + POSTRE 15%" — aplicables={matchas}, beneficiados={postres}.
    if ids_aplicables and ids_beneficiados:
        return bool(ids_aplicables & ids_carrito) and bool(ids_beneficiados & ids_carrito)

    # Combos o promos marcadas con requiere_todos_productos: exigen que TODOS
    # los productos_aplicables estén en el carrito.
    requiere_todos = (
        promo.tipo_descuento.descripcion == TD_COMBO
        or getattr(promo, "requiere_todos_productos", False)
    )
    if requiere_todos:
        if not ids_aplicables:
            return False
        return ids_aplicables.issubset(ids_carrito)

    # Resto: basta una intersección
    if not ids_aplicables:
        return False
    return bool(ids_aplicables & ids_carrito)


def promos_elegibles(carrito_items):
    """Lista de promos activas, vigentes hoy y elegibles para este carrito.

    Útil para que el cliente pueda elegir cuál aplicar.
    """
    from apps.menu.models import Promocion

    promos = (
        Promocion.objects
        .filter(activa=True)
        .prefetch_related("productos_aplicables", "productos_beneficiados")
        .select_related("tipo_descuento")
    )
    return [p for p in promos if p.aplica_hoy() and _promo_es_elegible(p, carrito_items)]


def aplicar_promociones(
    carrito_items: list[dict[str, Any]],
    sesion_cliente=None,
    promocion_id: int | None = None,
) -> tuple[list[dict[str, Any]], list[Any], list[Any]]:
    """Aplica UNA promoción al carrito (regla: máximo una promo por pedido).

    Parámetros
    ----------
    carrito_items:
        Lista de dicts con al menos: producto_id, cantidad, subtotal,
        modificadores, notas.
    sesion_cliente:
        Reservado para validaciones futuras (límite de usos por cliente).
    promocion_id:
        Si el cliente eligió explícitamente una promo, se aplica solo esa.
        Si es None: si solo hay una promo elegible, se aplica automáticamente;
        si hay varias, NO se aplica ninguna y se devuelven como opciones para
        que el cliente elija.

    Retorna
    -------
    (carrito_modificado, promociones_aplicadas, promociones_elegibles)
        - carrito_modificado: copia con subtotales ajustados y 'promocion_id'
          en los ítems afectados.
        - promociones_aplicadas: lista (0 o 1 elemento).
        - promociones_elegibles: todas las promos que el cliente podría elegir
          (incluye la aplicada). Permite al frontend mostrar el selector.
    """
    carrito = copy.deepcopy(carrito_items)

    elegibles = promos_elegibles(carrito)
    aplicadas: list[Any] = []

    if not elegibles:
        return carrito, aplicadas, []

    promo_a_aplicar = None
    if promocion_id is not None:
        for p in elegibles:
            if p.pk == int(promocion_id):
                promo_a_aplicar = p
                break
    elif len(elegibles) == 1:
        # Sin ambigüedad: se aplica automáticamente
        promo_a_aplicar = elegibles[0]
    # else: hay varias, esperamos elección explícita

    if promo_a_aplicar is not None:
        ids_aplicables = set(promo_a_aplicar.productos_aplicables.values_list("id", flat=True))
        _aplicar_una(carrito, promo_a_aplicar, ids_aplicables, aplicadas)

    return carrito, aplicadas, elegibles


# ─── Implementaciones por tipo ────────────────────────────────────────────────

def _aplicar_porcentaje(carrito, promo, ids_aplicables, aplicadas):
    if not promo.valor_descuento:
        return
    pct = Decimal(str(promo.valor_descuento)) / Decimal("100")
    ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
    ids_descuento = (ids_aplicables | ids_beneficiados) if (ids_aplicables and ids_beneficiados) else ids_aplicables
    afectados = False
    for item in carrito:
        if ids_descuento and item["producto_id"] not in ids_descuento:
            continue
        descuento = Decimal(str(item["subtotal"])) * pct
        item["subtotal"] = float(Decimal(str(item["subtotal"])) - descuento)
        item["promocion_id"] = promo.pk
        afectados = True
    if afectados and promo not in aplicadas:
        aplicadas.append(promo)


def _aplicar_monto_por_item(carrito, promo, ids_aplicables, aplicadas):
    if not promo.valor_descuento:
        return
    descuento = Decimal(str(promo.valor_descuento))
    ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
    ids_descuento = (ids_aplicables | ids_beneficiados) if (ids_aplicables and ids_beneficiados) else ids_aplicables
    afectados = False
    for item in carrito:
        if ids_descuento and item["producto_id"] not in ids_descuento:
            continue
        nuevo = max(Decimal("0"), Decimal(str(item["subtotal"])) - descuento)
        item["subtotal"] = float(nuevo)
        item["promocion_id"] = promo.pk
        afectados = True
    if afectados and promo not in aplicadas:
        aplicadas.append(promo)


def _aplicar_monto_total(carrito, promo, aplicadas):
    if not promo.valor_descuento:
        return
    total = sum(Decimal(str(i["subtotal"])) for i in carrito)
    if total <= 0:
        return
    descuento_total = Decimal(str(promo.valor_descuento))
    factor = max(Decimal("0"), (total - descuento_total) / total)
    for item in carrito:
        item["subtotal"] = float(Decimal(str(item["subtotal"])) * factor)
        item["promocion_id"] = promo.pk
    if promo not in aplicadas:
        aplicadas.append(promo)


def _aplicar_2x1(carrito, promo, ids_aplicables, aplicadas):
    """Cada 2 unidades del mismo producto, la más barata es gratis."""
    ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
    ids_descuento = (ids_aplicables | ids_beneficiados) if (ids_aplicables and ids_beneficiados) else ids_aplicables
    afectados = False
    for item in carrito:
        if ids_descuento and item["producto_id"] not in ids_descuento:
            continue
        cant = item["cantidad"]
        if cant < 2:
            continue
        pares = cant // 2
        precio_unitario = Decimal(str(item["subtotal"])) / Decimal(str(cant))
        descuento = precio_unitario * pares
        item["subtotal"] = float(Decimal(str(item["subtotal"])) - descuento)
        item["promocion_id"] = promo.pk
        afectados = True
    if afectados and promo not in aplicadas:
        aplicadas.append(promo)


def _aplicar_lleva_x_paga_y(carrito, promo, ids_aplicables, aplicadas):
    """
    Lleva cantidad_minima unidades, paga valor_descuento unidades.
    Ej. Lleva 3, paga 2 → cada grupo de 3, se descuenta 1.
    """
    if not promo.cantidad_minima or not promo.valor_descuento:
        return
    x = int(promo.cantidad_minima)          # cantidad a llevar
    y = int(promo.valor_descuento)           # cantidad a pagar
    if x <= y or x < 2:
        return
    ids_beneficiados = set(promo.productos_beneficiados.values_list("id", flat=True))
    ids_descuento = (ids_aplicables | ids_beneficiados) if (ids_aplicables and ids_beneficiados) else ids_aplicables
    afectados = False
    for item in carrito:
        if ids_descuento and item["producto_id"] not in ids_descuento:
            continue
        cant = item["cantidad"]
        if cant < x:
            continue
        grupos = cant // x
        unidades_gratis = grupos * (x - y)
        precio_unitario = Decimal(str(item["subtotal"])) / Decimal(str(cant))
        descuento = precio_unitario * unidades_gratis
        item["subtotal"] = float(Decimal(str(item["subtotal"])) - descuento)
        item["promocion_id"] = promo.pk
        afectados = True
    if afectados and promo not in aplicadas:
        aplicadas.append(promo)


def _aplicar_combo(carrito, promo, ids_aplicables, ids_beneficiados, aplicadas):
    """
    Si todos los productos_aplicables están en el carrito,
    reemplaza el subtotal de los productos_beneficiados por valor_descuento
    distribuido proporcionalmente.
    """
    if not promo.valor_descuento:
        return

    # Verificar que todos los productos requeridos están en el carrito
    ids_en_carrito = {item["producto_id"] for item in carrito}
    if ids_aplicables and not ids_aplicables.issubset(ids_en_carrito):
        return  # Falta al menos un producto del combo

    # Ítems beneficiados (o todos si no se especificaron)
    target_ids = ids_beneficiados if ids_beneficiados else ids_aplicables
    items_target = [i for i in carrito if i["producto_id"] in target_ids]
    if not items_target:
        return

    total_actual = sum(Decimal(str(i["subtotal"])) for i in items_target)
    if total_actual <= 0:
        return

    precio_combo = Decimal(str(promo.valor_descuento))
    factor = precio_combo / total_actual
    for item in items_target:
        item["subtotal"] = float(Decimal(str(item["subtotal"])) * factor)
        item["promocion_id"] = promo.pk

    if promo not in aplicadas:
        aplicadas.append(promo)
