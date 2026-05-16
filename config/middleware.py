"""
config/middleware.py
Middlewares globales de Mochi Matcha.
"""
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


class StaffSessionIsolationMiddleware:
    """
    Aísla la sesión Django por prefijo de ruta del staff.

    Django usa una única cookie 'sessionid' por navegador/dominio, lo que
    provoca que el login de cocina sobrescriba la sesión de mesero cuando
    ambos están abiertos en el mismo navegador. Este middleware asigna una
    cookie distinta por módulo (sid_mesero, sid_cocina, sid_gerente) de forma
    transparente, antes de que SessionMiddleware lea la cookie estándar.

    Debe declararse ANTES de SessionMiddleware en settings.MIDDLEWARE.
    """
    _ROLE_COOKIES = {
        '/mesero/': 'sid_mesero',
        '/cocina/':  'sid_cocina',
        '/gerente/': 'sid_gerente',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def _role_cookie(self, path):
        """Devuelve el nombre de cookie específico para la ruta dada, o None si no aplica."""
        for prefix, name in self._ROLE_COOKIES.items():
            if path.startswith(prefix):
                return name
        return None

    def __call__(self, request):
        from django.conf import settings
        std  = settings.SESSION_COOKIE_NAME   # 'sessionid'
        role = self._role_cookie(request.path)

        if role:
            if role in request.COOKIES:
                # Presentar la cookie de rol como la cookie estándar para que
                # SessionMiddleware cargue la sesión correcta del módulo.
                request.COOKIES[std] = request.COOKIES[role]
            elif std in request.COOKIES:
                # Hay un sessionid genérico de otra app — ocultarlo para
                # que este módulo arranque con sesión vacía.
                del request.COOKIES[std]

        response = self.get_response(request)

        if role and std in response.cookies:
            # SessionMiddleware escribió 'sessionid' — renombrarlo al nombre
            # específico del rol para que no colisione con otros módulos.
            m = response.cookies[std]
            try:
                max_age = int(m.get('max-age')) if m.get('max-age') else None
            except (ValueError, TypeError):
                max_age = None
            response.set_cookie(
                key=role,
                value=m.value,
                max_age=max_age,
                path=m.get('path', '/'),
                httponly=True,
                samesite='Lax',
            )
            del response.cookies[std]

        return response


# Rutas que NUNCA deben bloquearse en modo mantenimiento: login de staff,
# la propia página de mantenimiento, el panel de admin (para que el gerente
# pueda desactivar el modo mantenimiento desde allí) y los assets necesarios
# para que la página de mantenimiento renderice correctamente.
#
# /accounts/ es el login real del staff (genérico para todos los roles); los
# /<rol>/login/ son aliases que también deben pasar. Sin /accounts/ aquí, el
# propio gerente no puede entrar a apagar el modo mantenimiento.
EXCLUDED_PATHS = [
    '/mantenimiento/',
    '/admin/',
    '/accounts/',
    '/gerente/login/',
    '/gerente/logout/',
    '/mesero/login/',
    '/cocina/login/',
    '/static/',
    '/media/',
]


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    Middleware de modo mantenimiento configurable desde la BD.

    Cuando la clave 'modo_mantenimiento' en la tabla Configuracion tiene valor
    'true', '1' o 'yes', redirige todas las peticiones de clientes a la página
    /mantenimiento/. El staff autenticado (gerente, admin, is_staff) siempre
    pasa; también pasan las rutas definidas en EXCLUDED_PATHS.

    La consulta a BD se hace en cada request (no hay caché persistente entre
    procesos), lo que garantiza que activar/desactivar el modo sea inmediato.
    """
    def process_request(self, request):
        # Siempre permitir rutas excluidas
        path = request.path_info
        if any(path.startswith(p) for p in EXCLUDED_PATHS):
            return None

        # Siempre permitir staff/superusers autenticados
        if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'rol', '') in ('gerente', 'admin')):
            return None

        # Verificar en BD (con caché simple en memoria por proceso)
        try:
            from apps.gerente.models import Configuracion
            cfg = Configuracion.objects.filter(clave='modo_mantenimiento').first()
            if cfg and cfg.valor.lower() in ('true', '1', 'yes'):
                return redirect('/mantenimiento/')
        except Exception:
            # Si la tabla no existe aún (primera migración), no bloquear
            pass

        return None


class HorarioAtencionMiddleware(MiddlewareMixin):
    """
    Middleware de horarios de atención (Fase 3.1).

    Si la clave de configuración `horarios_activos` está en "true" y la hora
    actual queda fuera del horario habilitado para el día actual, redirige
    a /cerrado/. Igual que el modo mantenimiento, el staff y las rutas en
    EXCLUDED_PATHS pasan siempre — el gerente puede entrar a apagar la opción
    en cualquier momento.

    Estrategia preferida: dejar el Docker corriendo siempre y bloquear con
    este middleware. Encender/apagar contenedores por horario es frágil
    (pierdes la cache de promociones, las sesiones activas, los pedidos
    parcialmente preparados, etc.). Esto NO frena al staff que llega antes
    de abrir para preparar.

    Cache: 30 s en memoria del proceso. Cambios desde el panel del gerente
    tardan a lo sumo medio minuto en propagarse, lo que es aceptable y
    evita N queries por request.
    """
    _cache_horarios = None
    _cache_activos  = None
    _cache_until    = 0.0

    def process_request(self, request):
        path = request.path_info
        if any(path.startswith(p) for p in EXCLUDED_PATHS):
            return None
        # /cerrado/ siempre accesible (la propia página) — no en EXCLUDED_PATHS
        # para no confundirlo con el modo mantenimiento.
        if path.startswith('/cerrado/'):
            return None
        if request.user.is_authenticated and (
            request.user.is_staff
            or getattr(request.user, 'rol', '') in ('gerente', 'admin', 'mesero', 'cocina')
        ):
            return None

        try:
            self._refresh_cache()
        except Exception:
            return None  # BD aún no migrada — no bloquear

        if not self._cache_activos:
            return None  # gerente decidió que la app está siempre abierta

        if not self._cache_horarios:
            # Hay flag activo pero NO se configuró ningún horario aún. No
            # bloqueamos — el gerente puede configurarlos sin quedar fuera.
            return None

        from django.utils import timezone
        ahora = timezone.localtime(timezone.now())
        hoy = ahora.weekday()
        hora = ahora.time()
        # ¿Hay algún rango habilitado para HOY que cubra la hora actual?
        for h in self._cache_horarios:
            if h['activo'] and h['dia_semana'] == hoy and self._cubre(h, hora):
                return None

        return redirect('/cerrado/')

    @staticmethod
    def _cubre(h, hora_actual):
        if h['abre'] <= h['cierra']:
            return h['abre'] <= hora_actual < h['cierra']
        return hora_actual >= h['abre'] or hora_actual < h['cierra']

    @classmethod
    def _refresh_cache(cls):
        import time as _t
        now = _t.time()
        if now < cls._cache_until and cls._cache_horarios is not None:
            return
        from apps.gerente.models import Configuracion, HorarioAtencion
        cfg = Configuracion.objects.filter(clave='horarios_activos').first()
        cls._cache_activos = bool(cfg and cfg.valor.lower() in ('true', '1', 'yes'))
        cls._cache_horarios = [
            {'dia_semana': h.dia_semana, 'abre': h.abre, 'cierra': h.cierra, 'activo': h.activo}
            for h in HorarioAtencion.objects.all()
        ]
        cls._cache_until = now + 30  # invalidar a los 30 s

    @classmethod
    def invalidate(cls):
        """Llamar tras editar HorarioAtencion para que el cambio se vea inmediato."""
        cls._cache_until = 0.0
