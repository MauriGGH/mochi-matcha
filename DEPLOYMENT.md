# 🚀 Guía de Despliegue — Mochi Matcha

> Guía completa para desplegar, actualizar y mantener Mochi Matcha en producción.  
> Infraestructura: **Raspberry Pi** + **Docker Compose** + **Cloudflare Tunnel** + **Nginx Proxy Manager**.

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Despliegue inicial](#2-despliegue-inicial)
3. [Configuración de red (Cloudflare + NPM)](#3-configuración-de-red-cloudflare--nginx-proxy-manager)
4. [Variables de entorno (.env)](#4-variables-de-entorno-env)
5. [Actualizar código en producción](#5-actualizar-código-en-producción)
6. [Configuración desde la UI (PayPal, KDS)](#6-configuración-desde-la-ui)
7. [Backups](#7-backups)
8. [Comandos útiles](#8-comandos-útiles)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Requisitos previos

En el servidor (Raspberry Pi u otro host Linux):

- Docker Engine ≥ 24
- Docker Compose plugin (`docker compose`, no `docker-compose`)
- Acceso SSH configurado (preferiblemente con clave pública)
- Cuenta de Cloudflare con un dominio configurado
- Nginx Proxy Manager corriendo en Docker

Verifica que Docker funciona:

```bash
docker --version
docker compose version
```

---

## 2. Despliegue inicial

### 2.1 Clonar / copiar el proyecto

```bash
# En el servidor
mkdir -p ~/pi/docker/mochi-matcha-production
cd ~/pi/docker/mochi-matcha-production

# Copia los archivos desde tu máquina local
# (desde tu PC, no desde el servidor)
scp -r /ruta/local/mochi-matcha-production/* mau@julian.tail62ca00.ts.net:~/pi/docker/mochi-matcha-production/
```

### 2.2 Crear el archivo `.env`

```bash
cp .env.example .env   # si existe
nano .env              # o edítalo directamente
```

Ver la sección [Variables de entorno](#4-variables-de-entorno-env) para los valores requeridos.

### 2.3 Levantar los contenedores

```bash
cd ~/pi/docker/mochi-matcha-production
docker compose up -d --build
```

El primer arranque:
1. Construye la imagen de Django (instala dependencias, corre `collectstatic`)
2. Levanta MariaDB
3. Espera a que la BD esté sana (healthcheck) antes de iniciar Django

### 2.4 Aplicar migraciones

```bash
docker compose exec web python manage.py migrate
```

### 2.5 Cargar datos iniciales (seed)

```bash
docker compose exec web python manage.py shell -c "exec(open('seed.py').read())"
```

El seed carga los catálogos básicos (métodos de pago, roles, etc.).

### 2.6 Crear usuario gerente

```bash
docker compose exec web python manage.py shell
```

```python
from apps.accounts.models import Empleado
e = Empleado.objects.create_user(
    username='gerente',
    password='tu-contraseña-segura',
    nombre='Nombre Gerente',
    rol='gerente'
)
e.save()
exit()
```

### 2.7 Verificar que Django responde

```bash
curl http://localhost:8002/gerente/login/
# Debe devolver HTML con código 200
```

---

## 3. Configuración de red (Cloudflare + Nginx Proxy Manager)

### Flujo del tráfico

```
Internet → Cloudflare Edge (TLS) → cloudflared (host) → localhost:80 → NPM → 172.x.x.1:8002 → Django
```

### 3.1 Cloudflare Tunnel

`cloudflared` debe correr con `network_mode: host` para poder alcanzar `localhost:80`.

En el panel de Cloudflare Tunnel, la aplicación debe apuntar a:
```
http://localhost:80
```

### 3.2 Nginx Proxy Manager

En el Proxy Host para tu dominio (`mochi-matcha.tu-dominio.com`):

- **Forward Hostname/IP:** `172.x.x.1` (IP del bridge de Docker en el host — verificar con `ip route | grep docker`)
- **Forward Port:** `8002`
- **Force SSL:** activado

En la pestaña **Advanced** del proxy host, agrega:

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

En el archivo de configuración de NPM (`/data/nginx/proxy_host/<id>.conf` dentro del contenedor NPM), asegúrate de que:

```nginx
set $trust_forwarded_proto "T";
```

Esto evita el loop de redirección 301 cuando Cloudflare envía `X-Forwarded-Proto: https`.

### 3.3 Django — puerto del contenedor

En `docker-compose.yml`, el binding de puerto debe ser:

```yaml
ports:
  - "8002:8000"   # sin 127.0.0.1: para que NPM pueda alcanzarlo
```

> **Nota:** `127.0.0.1:8002:8000` restringe el acceso solo al loopback del host — NPM (en Docker) no puede alcanzarlo así.

---

## 4. Variables de entorno (`.env`)

Crea este archivo en la raíz del proyecto en el servidor. **Nunca lo subas a git.**

```env
# ── Base de datos ────────────────────────────────────────────
MYSQL_DATABASE=mochi_matcha
MYSQL_USER=mochi_user
MYSQL_PASSWORD=contraseña-segura-db
MYSQL_ROOT_PASSWORD=contraseña-root-segura
DB_HOST=db
DB_PORT=3306

# ── Django ───────────────────────────────────────────────────
SECRET_KEY=genera-una-clave-larga-y-aleatoria-aqui
DEBUG=False
ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com

# ── PayPal (fallback — se puede sobreescribir desde la UI) ───
PAYPAL_CLIENT_ID=tu-client-id
PAYPAL_SECRET=tu-secret
PAYPAL_MODO=live     # o "sandbox" para pruebas

# ── Media ────────────────────────────────────────────────────
MEDIA_ROOT=/app/media
```

> **Prioridad de credenciales PayPal:**  
> Los valores guardados en `Configuración` del panel del gerente tienen **prioridad** sobre el `.env`.  
> El `.env` actúa solo como fallback para instalaciones nuevas.

Para generar un `SECRET_KEY` seguro:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 5. Actualizar código en producción

Como el código está **dentro de la imagen Docker** (no montado como volumen), el proceso para actualizar es:

### 5.1 Enviar solo los archivos modificados

Desde tu máquina local, ejecuta `scp` solo para los archivos que cambiaron:

```bash
BASE_LOCAL="/ruta/local/mochi-matcha-production"
BASE_REMOTE="mau@julian.tail62ca00.ts.net:~/pi/docker/mochi-matcha-production"

# Ejemplo: actualizar templates y views del gerente
scp "$BASE_LOCAL/apps/gerente/templates/gerente/reportes_avanzados.html" \
    "$BASE_REMOTE/apps/gerente/templates/gerente/"

scp "$BASE_LOCAL/apps/gerente/views.py" "$BASE_REMOTE/apps/gerente/"
scp "$BASE_LOCAL/apps/gerente/urls.py"  "$BASE_REMOTE/apps/gerente/"
```

### 5.2 Reconstruir la imagen y reiniciar

```bash
ssh mau@julian.tail62ca00.ts.net \
  "cd ~/pi/docker/mochi-matcha-production && docker compose up -d --build web"
```

Este comando:
1. Reconstruye la imagen de Django con los archivos actualizados
2. Recrea el contenedor `web` con la nueva imagen
3. Deja la BD corriendo sin interrupciones

> **Por qué no usar `rsync --delete`:**  
> Las carpetas de dev y producción pueden tener diferencias (migraciones, archivos de configuración exclusivos de producción). Usar `--delete` entre proyectos distintos puede borrar archivos que no existen en dev pero sí en producción. Siempre usa `scp` con archivos específicos.

### 5.3 Si hubo nuevas migraciones

```bash
ssh mau@julian.tail62ca00.ts.net \
  "cd ~/pi/docker/mochi-matcha-production && docker compose exec web python manage.py migrate"
```

---

## 6. Configuración desde la UI

Algunas configuraciones se pueden cambiar **sin tocar el servidor** desde el panel del gerente en `/gerente/configuracion/`:

| Configuración | Clave en BD | Descripción |
|---|---|---|
| PayPal Client ID | `paypal_client_id` | Credencial de la app PayPal |
| PayPal Secret | `paypal_secret` | Credencial secreta PayPal |
| Modo PayPal | `paypal_modo` | `live` o `sandbox` |
| Modo mantenimiento | `mantenimiento` | `true` bloquea el acceso de clientes |
| Umbrales KDS | `kds_umbral_*` | Tiempos del semáforo de cocina |

Los cambios toman efecto en la siguiente solicitud — **no requieren reiniciar el contenedor**.

---

## 7. Backups

### 7.1 Base de datos

```bash
# Exportar
ssh mau@julian.tail62ca00.ts.net \
  "docker exec mochi_matcha_db mysqldump -u mochi_user -p'contraseña' mochi_matcha > ~/backup_$(date +%Y%m%d).sql"

# Descargar el backup a tu máquina local
scp mau@julian.tail62ca00.ts.net:~/backup_$(date +%Y%m%d).sql ./backups/
```

### 7.2 Archivos de media (imágenes)

```bash
# Los archivos de media están en ./media/ en el host (bind mount)
scp -r mau@julian.tail62ca00.ts.net:~/pi/docker/mochi-matcha-production/media/ ./backups/media/
```

### 7.3 Restaurar BD

```bash
# Copiar el backup al servidor
scp backup.sql mau@julian.tail62ca00.ts.net:~/

# Restaurar
ssh mau@julian.tail62ca00.ts.net \
  "docker exec -i mochi_matcha_db mysql -u mochi_user -p'contraseña' mochi_matcha < ~/backup.sql"
```

---

## 8. Comandos útiles

```bash
# Ver logs del contenedor Django en tiempo real
ssh mau@julian.tail62ca00.ts.net \
  "docker compose -f ~/pi/docker/mochi-matcha-production/docker-compose.yml logs -f web"

# Ver logs de la BD
ssh mau@julian.tail62ca00.ts.net \
  "docker compose -f ~/pi/docker/mochi-matcha-production/docker-compose.yml logs -f db"

# Reiniciar solo Django (sin rebuild)
ssh mau@julian.tail62ca00.ts.net \
  "cd ~/pi/docker/mochi-matcha-production && docker compose restart web"

# Entrar al contenedor de Django
ssh mau@julian.tail62ca00.ts.net \
  "docker exec -it mochi_matcha_web bash"

# Ver estado de los contenedores
ssh mau@julian.tail62ca00.ts.net \
  "docker compose -f ~/pi/docker/mochi-matcha-production/docker-compose.yml ps"

# Verificar conectividad NPM → Django (desde dentro del contenedor NPM)
docker exec nginx-proxy-manager curl -s http://172.x.x.1:8002/gerente/login/ | head -5
```

---

## 9. Troubleshooting

### ❌ Error 502 Bad Gateway

NPM no puede alcanzar Django.

1. Verifica que el contenedor `web` está corriendo: `docker compose ps`
2. Verifica la IP del bridge: `ip route | grep docker` → busca la IP del host en la red de Docker
3. En el Proxy Host de NPM, usa esa IP (ej. `172.19.0.1`) como Forward Hostname, **no** `localhost`
4. Verifica que el puerto no esté limitado a loopback en `docker-compose.yml` (debe ser `"8002:8000"`, no `"127.0.0.1:8002:8000"`)

### ❌ Error 301 — Redirect loop

Cloudflare envía HTTP a NPM pero NPM tiene Force SSL activo.

En el config de NPM (`/data/nginx/proxy_host/<id>.conf` dentro del contenedor):

```nginx
set $trust_forwarded_proto "T";
```

Esto le indica a NPM que confíe en el header `X-Forwarded-Proto: https` de Cloudflare.

### ❌ Los cambios de código no se ven

El código está dentro de la imagen Docker. Un simple `restart` no aplica cambios de código. Debes reconstruir:

```bash
docker compose up -d --build web
```

### ❌ Imágenes 404 en producción

Las imágenes de productos se sirven desde `/media/`. Verifica:

1. Que `./media` en el host tiene los archivos: `ls ~/pi/docker/mochi-matcha-production/media/images/`
2. Que `urls.py` tiene la ruta de media activa (sin guardia `if DEBUG`)
3. Que el bind mount en `docker-compose.yml` es `./media:/app/media`

### ❌ PayPal no procesa pagos

1. Verifica el modo en `Configuración` del gerente: debe ser `live` para producción
2. Verifica que `paypal_client_id` y `paypal_secret` en la BD corresponden a una app de PayPal **live** (no sandbox)
3. Revisa los logs: `docker compose logs -f web | grep -i paypal`

### ❌ Error al aplicar migraciones

```bash
docker compose exec web python manage.py showmigrations   # ver estado
docker compose exec web python manage.py migrate --run-syncdb  # forzar sync
```

---

<div align="center">

*Guía mantenida junto con el código fuente en [`mochi-matcha-production/`](README.md).*

</div>
