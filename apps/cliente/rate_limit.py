"""
Contingencias contra abuso del cliente (Fase 2.3).

Limita la frecuencia con que UNA sesión de cliente puede llamar a endpoints
sensibles. Usa la cache de Django (back-end por defecto: LocMemCache, o Redis
en producción) para registrar timestamps recientes de cada acción.

Límites (vigentes a la fecha):
  - confirmar_pedido     → 5 pedidos por sesión en 60 s.
  - solicitar_ayuda      → 1 alerta cada 30 s + máx 3 alertas vivas no atendidas.
  - solicitar_cuenta     → 1 solicitud nueva cada 30 s (el resto pasa por
                           get_or_create y no llega aquí).

Cada función devuelve None si la acción es permitida, o un JsonResponse 429
con `retry_after` en segundos para que el frontend muestre el mensaje al cliente
sin tener que adivinar el cooldown.
"""
from __future__ import annotations

import time
from django.core.cache import cache
from django.http import JsonResponse


def _bucket_key(prefix: str, sesion_id: int) -> str:
    """Clave del bucket por sesión y tipo de acción."""
    return f"rl:{prefix}:s{sesion_id}"


def _consume(prefix: str, sesion_id: int, limit: int, window_s: int) -> int:
    """
    Registra el "ahora" en el bucket de la sesión. Devuelve cuántos segundos
    debe esperar el cliente, o 0 si la acción está permitida.

    Implementación: lista de timestamps recientes en la cache. Descartamos los
    que cayeron fuera de la ventana, agregamos el actual y comparamos con el
    límite. La cache se asienta con TTL = window_s para limpieza automática.
    """
    key = _bucket_key(prefix, sesion_id)
    now = time.time()
    horizon = now - window_s
    historial = [t for t in (cache.get(key) or []) if t > horizon]

    if len(historial) >= limit:
        # Cuánto falta para que el evento MÁS ANTIGUO salga de la ventana.
        retry_after = max(1, int(horizon - historial[0]) * -1)
        cache.set(key, historial, timeout=window_s + 5)
        return retry_after

    historial.append(now)
    cache.set(key, historial, timeout=window_s + 5)
    return 0


def too_many(retry_after: int, mensaje: str) -> JsonResponse:
    """
    Construye la respuesta 429 estándar. `retry_after` se devuelve en el JSON
    (`retry_after`) y en el header HTTP (`Retry-After`) — el frontend usa el
    primero, los proxies/CDN el segundo.
    """
    resp = JsonResponse({
        "ok": False,
        "error": mensaje,
        "retry_after": retry_after,
        "rate_limited": True,
    }, status=429)
    resp["Retry-After"] = str(retry_after)
    return resp


# ── Límites por endpoint ─────────────────────────────────────────────────────

def check_confirmar_pedido(sesion_id: int):
    """
    Máximo 5 pedidos por sesión en 60 s. Bloquea ráfagas de "spamear pedidos"
    sin frenar el caso real de un cliente que pide algo, cambia de opinión y
    pide algo más al rato.
    """
    retry = _consume("pedido", sesion_id, limit=5, window_s=60)
    if retry:
        return too_many(
            retry,
            f"Estás enviando pedidos demasiado seguido. Espera {retry} s e intenta de nuevo.",
        )
    return None


def check_solicitar_ayuda(sesion_id: int, alertas_vivas: int):
    """
    1 alerta cada 30 s + máx 3 alertas no atendidas vivas. Si el mesero todavía
    no atiende las anteriores, no tiene sentido seguir avisándole.
    """
    if alertas_vivas >= 3:
        return too_many(
            30,
            "Tienes varias alertas sin atender. Espera a que tu mesero llegue.",
        )
    retry = _consume("ayuda", sesion_id, limit=1, window_s=30)
    if retry:
        return too_many(
            retry,
            f"Acabas de llamar al mesero. Espera {retry} s antes de volver a llamarlo.",
        )
    return None


def check_solicitar_cuenta(sesion_id: int):
    """
    1 solicitud cada 30 s. La idempotencia del backend ya impide duplicados
    con la MISMA configuración (tipo / método); este límite frena el patrón
    de "solicitar individual, cancelar, solicitar grupal" en loop.
    """
    retry = _consume("cuenta", sesion_id, limit=1, window_s=30)
    if retry:
        return too_many(
            retry,
            f"Espera {retry} s antes de pedir la cuenta de nuevo.",
        )
    return None
