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


def aplicar_promociones(
    carrito_items: list[dict[str, Any]],
    sesion_cliente=None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    """
    Aplica promociones activas y vigentes al carrito.

    Parámetros
    ----------
    carrito_items:
        Lista de dicts con al menos las claves:
            producto_id (int), cantidad (int), subtotal (float),
            modificadores (list), notas (str)
    sesion_cliente:
        Instancia de SesionCliente (opcional, reservado para validaciones futuras
        como límite de usos por cliente).

    Retorna
    -------
    (carrito_modificado, promociones_aplicadas)
        carrito_modificado: copia del carrito con subtotales ajustados y
            campo extra 'promocion_id' cuando aplica.
        promociones_aplicadas: lista de instancias Promocion que se aplicaron.
    """
    from apps.menu.models import Promocion

    ahora = timezone.now()
    promos_activas = (
        Promocion.objects
        .filter(activa=True, fecha_inicio__lte=ahora, fecha_fin__gte=ahora)
        .prefetch_related("productos_aplicables", "productos_beneficiados")
        .select_related("tipo_descuento")
    )

    carrito = copy.deepcopy(carrito_items)
    aplicadas: list[Any] = []

    for promo in promos_activas:
        if promo.tipo_descuento is None:
            continue

        tipo = promo.tipo_descuento.descripcion
        ids_aplicables = set(promo.productos_aplicables.values_list("id", flat=True))

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

    return carrito, aplicadas


# ─── Implementaciones por tipo ────────────────────────────────────────────────

def _aplicar_porcentaje(carrito, promo, ids_aplicables, aplicadas):
    if not promo.valor_descuento:
        return
    pct = Decimal(str(promo.valor_descuento)) / Decimal("100")
    afectados = False
    for item in carrito:
        if ids_aplicables and item["producto_id"] not in ids_aplicables:
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
    afectados = False
    for item in carrito:
        if ids_aplicables and item["producto_id"] not in ids_aplicables:
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
    afectados = False
    for item in carrito:
        if ids_aplicables and item["producto_id"] not in ids_aplicables:
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
    afectados = False
    for item in carrito:
        if ids_aplicables and item["producto_id"] not in ids_aplicables:
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
