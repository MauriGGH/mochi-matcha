"""
config/settings.py — Configuración central del proyecto Django "Mochi Matcha".

Todas las variables sensibles se leen desde variables de entorno para separar
configuración del código (12-factor app). Si una variable no está definida,
se usa un valor por defecto apropiado para desarrollo local.

Variables de entorno relevantes:
  SECRET_KEY, DEBUG, ALLOWED_HOSTS, SITE_BASE_URL
  MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_PORT
  PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_MODO
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-key-change-in-production')

# FIX: DEBUG default False (era 'True')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')

# URL base del sitio para generación de QR y links absolutos
SITE_BASE_URL = os.environ.get('SITE_BASE_URL', 'http://localhost:8000')

# PayPal
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID', '')
PAYPAL_SECRET    = os.environ.get('PAYPAL_SECRET', '')
PAYPAL_MODO      = os.environ.get('PAYPAL_MODO', 'sandbox')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # FIX: rutas actualizadas a apps.*
    # Módulos de datos (núcleo)
    'apps.accounts',   # modelo Empleado (AUTH_USER_MODEL)
    'apps.catalogs',   # catálogos auxiliares (ModalidadIngreso, MetodoPago, etc.)
    'apps.menu',       # Categoria, Producto, Modificadores, Promociones
    'apps.mesas',      # Mesa, SesionCliente, AlertaMesero
    'apps.pedidos',    # Pedido, DetallePedido, SolicitudPago
    'apps.auditoria',  # log de acciones del sistema
    # Módulos de interfaz (por rol)
    'apps.cliente',    # menú digital del cliente (QR)
    'apps.mesero',     # panel de mesero (mapa de mesas, alertas, entregas)
    'apps.cocina',     # KDS (Kitchen Display System) para cocina y bar
    'apps.gerente',    # dashboard, reportes, configuración
]

# FIX: apunta a apps.accounts
AUTH_USER_MODEL = 'accounts.Empleado'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Debe ir ANTES de SessionMiddleware: reescribe la cookie de sesión por módulo.
    'config.middleware.StaffSessionIsolationMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # FIX: ruta actualizada a apps.cliente
    # Inyecta request.sesion_cliente para las vistas del menú digital.
    'apps.cliente.middleware.ClienteSessionMiddleware',
    # Modo mantenimiento (después de auth para detectar staff)
    'config.middleware.MaintenanceModeMiddleware',
    # Horarios de atención (3.1): bloquea clientes fuera de horario
    'config.middleware.HorarioAtencionMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('MYSQL_DATABASE', 'mochi_matcha'),
        'USER': os.environ.get('MYSQL_USER', 'root'),
        'PASSWORD': os.environ.get('MYSQL_PASSWORD', ''),
        'HOST': os.environ.get('MYSQL_HOST', 'db'),
        'PORT': os.environ.get('MYSQL_PORT', '3306'),
        'OPTIONS': {
            # utf8mb4 = UTF-8 completo (incluye emojis 4-byte). Sin esto, la
            # conexión cae a utf8mb3 y los INSERT con 🍵, etc. revientan con
            # OperationalError 1366 "Incorrect string value".
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES', NAMES utf8mb4",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'  # Zona horaria de México central
USE_I18N = True
USE_TZ = True  # Usar fechas con timezone en la BD; timezone.now() devuelve UTC

# FIX: STATIC_URL con slashes correctas
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CSRF_TRUSTED_ORIGINS: dominios desde los que Django acepta POST con el header Origin.
# ngrok-free.app se incluye para pruebas con túnel público en desarrollo.
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://*.ngrok-free.app'  # ← Añade esta línea
]