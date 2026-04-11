

# ── Modelo de usuario personalizado ─────────────────────────────────────
from mochimatcha2.config.settings import BASE_DIR


AUTH_USER_MODEL = "accounts.Empleado"

# ── Apps instaladas ──────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Datos del negocio
    "accounts",
    "catalogs",
    "menu",
    "mesas",
    "pedidos",
    "auditoria",

    # Módulos de interfaz
    "cliente",
    "mesero",
    "cocina",
    "gerente",
]

# ── Middleware (orden importante) ────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # ▼ Middleware propio — debe ir DESPUÉS de SessionMiddleware
    "cliente.middleware.ClienteSessionMiddleware",
]

# ── Templates ────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],       # templates/base/ aquí
        "APP_DIRS": True,                        # carga templates/<app>/
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Archivos estáticos ───────────────────────────────────────────────────
STATIC_URL  = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]       # static/css/mochi.css etc.

# ── Sesiones (para el carrito del cliente) ───────────────────────────────
SESSION_COOKIE_AGE     = 7200   # 2 horas (coincide con la cookie de cliente)
SESSION_ENGINE         = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# ── Seguridad (producción) ───────────────────────────────────────────────
# SESSION_COOKIE_SECURE = True     # descomenta con HTTPS
# CSRF_COOKIE_SECURE    = True
# SECURE_SSL_REDIRECT   = True

# ── Login / Logout redirects ─────────────────────────────────────────────
LOGIN_URL           = "/accounts/login/"
LOGIN_REDIRECT_URL  = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# ── Sesión de staff: 30 min de inactividad (RF-035) ──────────────────────
# Implementado en el decorador + middleware — no en SESSION_COOKIE_AGE
# para no afectar al carrito del cliente.
STAFF_SESSION_TIMEOUT = 1800  # segundos
