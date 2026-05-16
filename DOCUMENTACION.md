# 🍵 Mochi Matcha — Documentación del Proyecto

> Sistema de gestión integral para cafetería: pedidos por QR, panel de mesero,
> display de cocina (KDS) y panel de administración.

**Versión:** 1.0
**Última actualización de la documentación:** mayo 2026

---

## 1. Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11 · Django 4.x |
| Base de datos | MariaDB 10.6 (charset `utf8mb4`) |
| Infraestructura | Docker · Docker Compose |
| Frontend | Plantillas Django · Bootstrap 5.3 · JavaScript vanilla |
| Gráficas | Chart.js |
| Recorte de imágenes | Cropper.js |
| Generación de PDF | WeasyPrint |
| Pagos en línea | PayPal REST API (SDK JS + REST) |
| Códigos QR | librería `qrcode` |
| Servidor de desarrollo | `manage.py runserver` dentro del contenedor `web` |

El proyecto se ejecuta como **dos contenedores**: `web` (Django) y `db` (MariaDB).

---

## 2. Arquitectura general

El proyecto sigue la estructura estándar de Django con **apps por dominio**. Cada
app encapsula un módulo funcional del negocio.

```
mochi-matcha/
├── config/                  # Configuración del proyecto Django
│   ├── settings.py           # Settings (BD, apps, middleware, PayPal, etc.)
│   ├── middleware.py         # Aislamiento de sesión por rol + modo mantenimiento
│   ├── urls.py               # URLconf raíz: enruta a cada app
│   ├── wsgi.py / asgi.py     # Puntos de entrada del servidor
│
├── apps/
│   ├── accounts/             # Usuario custom (Empleado), login staff, decoradores de rol
│   ├── catalogs/             # Catálogos auxiliares: ModalidadIngreso, MetodoPago, EstadoSolicitud
│   ├── mesas/                # Mesa, UbicacionMesa, SesionCliente, AlertaMesero  + QR
│   ├── menu/                 # Categoria, Producto, Modificadores, Promociones, descuentos
│   ├── pedidos/              # Pedido, DetallePedido, SolicitudPago + motor de promociones (utils.py)
│   ├── auditoria/            # Registro de acciones sensibles (Auditoria)
│   ├── cliente/              # App del CLIENTE final (sin login Django, cookie de sesión)
│   ├── mesero/               # Panel del MESERO (mapa de mesas, cobro, pedido asistido)
│   ├── cocina/               # KDS — Kitchen Display System
│   └── gerente/              # Panel de ADMINISTRACIÓN (CRUD, reportes, configuración)
│
├── templates/
│   └── base/                 # Plantillas base: cliente_base, staff_base, login
│
├── static/
│   ├── css/                  # mochi.css (tokens), cliente.css, staff.css
│   └── js/                   # table-pagination.js (paginación reutilizable)
│
├── seed.py                   # Script de población de datos de demostración
├── docker-compose.yml        # Definición de servicios web + db
├── Dockerfile                # Imagen del contenedor web
└── DOCUMENTACION.md          # Este archivo
```

### Apps de **dominio de datos** (modelos compartidos)

- **`accounts`** — modelo de usuario `Empleado` (autenticación del staff por `usuario`),
  con campo `rol` (`mesero` / `cocina` / `gerente` / `admin`). Incluye los decoradores
  de control de acceso (`@mesero_requerido`, `@cocina_requerido`, `@gerente_requerido`).
- **`catalogs`** — catálogos pequeños e inmutables: modalidades de ingreso, métodos
  de pago, estados de solicitud.
- **`mesas`** — `Mesa`, `UbicacionMesa`, `SesionCliente`, `AlertaMesero`. La `Mesa`
  genera su código QR; la `SesionCliente` representa al grupo de clientes sentados.
- **`menu`** — catálogo de productos: `Categoria`, `Producto`, `GrupoModificador`,
  `OpcionModificador`, `Promocion` y sus tipos de descuento.
- **`pedidos`** — `Pedido`, `DetallePedido`, `DetalleModificador`, `SolicitudPago`.
  `utils.py` contiene el **motor de promociones** (`aplicar_promociones`).
- **`auditoria`** — registro de acciones relevantes (pagos, cancelaciones, etc.).

### Apps de **interfaz** (una por tipo de usuario)

- **`cliente`** — lo que ve el comensal en su teléfono. No usa login de Django:
  la identidad se mantiene con una cookie (`mm_session`) gestionada por
  `cliente/middleware.py`.
- **`mesero`** — panel operativo del personal de piso.
- **`cocina`** — pantalla de cocina/barra (KDS).
- **`gerente`** — back-office: gestión de menú, mesas, empleados, reportes y configuración.

### Middlewares clave (`config/middleware.py`)

- **`StaffSessionIsolationMiddleware`** — aísla la cookie de sesión de Django por
  prefijo de ruta (`/mesero/`, `/cocina/`, `/gerente/`). Permite tener los tres
  paneles abiertos en el mismo navegador sin que un login pise al otro.
- **`MaintenanceModeMiddleware`** — si el modo mantenimiento está activo, redirige
  a los clientes a una pantalla informativa; el staff autenticado sigue pasando.
- **`ClienteSessionMiddleware`** (`apps/cliente/middleware.py`) — resuelve
  `request.sesion_cliente` a partir de la cookie `mm_session`; reconoce sesiones
  `activa` y `pagada` (para no expulsar al cliente tras el pago).

---

## 3. Flujo de la aplicación (narrativa end-to-end)

### 3.1 Llegada del cliente

1. El cliente **escanea el QR** de su mesa. El QR apunta a `/bienvenida/?mesa=<id>`.
   La URL se construye con el **dominio real del request**, por lo que funciona en
   producción sin reconfigurar nada.
2. En **bienvenida**:
   - Si la mesa está libre → el cliente elige un alias y se crea su `SesionCliente`.
     Si es el primer cliente de la mesa, el sistema **genera un PIN** que se muestra
     en pantalla.
   - Si la mesa ya está ocupada → puede entrar como **"Soy nuevo"** (otra sesión en
     la misma mesa) o **"Recuperar sesión"** ingresando alias + PIN.
3. Se guarda la cookie `mm_session`. A partir de aquí el middleware del cliente
   identifica cada petición.
4. **Varios clientes** pueden compartir mesa: cada uno tiene su propia `SesionCliente`,
   pero todas comparten la `Mesa` y su PIN.

### 3.2 Pedidos

1. El cliente navega el **menú** (productos por categoría, con modificadores y
   carrusel de promociones).
2. Agrega productos al **carrito**. Antes de confirmar, el sistema calcula y muestra
   el **descuento aplicable**:
   - Si solo hay **una promoción elegible**, se aplica automáticamente.
   - Si hay **varias**, aparece un selector para que el cliente elija una
     (regla de negocio: **máximo una promoción por pedido**).
3. Al confirmar, se crea un `Pedido` con sus `DetallePedido`. Cada pedido lleva un
   **token de idempotencia** que evita duplicados por doble-click o reintentos.
4. Alternativamente, el **mesero** puede hacer un **pedido asistido** desde su panel,
   en nombre de una sesión concreta (mismo flujo de promociones).
5. El pedido entra al **KDS**, repartido por **área** según la categoría de cada
   producto (`cocina` / `bar` / `ambos`).

### 3.3 Cocina (KDS)

1. Cada área (cocina o bar) ve solo los ítems que le corresponden.
2. El operador pulsa **"Comenzar preparación"** (el pedido pasa a `preparando`) y
   luego **"Marcar como listo"** (marca como listos **solo los ítems de su área**).
3. Un **pedido mixto** (comida + bebida) permanece en `preparando` hasta que
   **todas** las áreas terminan sus ítems; solo entonces pasa a `listo` global.
4. Un **pedido de una sola área** pasa a `listo` en cuanto esa área lo marca.
5. El **semáforo de tiempos** colorea cada ticket (verde / amarillo / rojo) según
   los minutos transcurridos; los umbrales los configura el gerente.

### 3.4 Pago

1. El cliente solicita la cuenta desde su app, eligiendo:
   - **Individual** — solo su consumo. Se cierra **únicamente su sesión**.
   - **Toda la mesa** — el consumo de todas las sesiones activas. Se cierran
     **todas las sesiones** y la mesa se libera.
2. El mesero ve la solicitud en su panel y procesa el cobro. El total se
   **recalcula en vivo** al abrir el modal (por si el cliente pidió algo más).
3. **Métodos de pago:** efectivo (con cálculo de cambio), tarjeta, mixto
   (efectivo + tarjeta) y **PayPal** (que el propio cliente paga desde su app).
4. Se puede añadir **propina** (porcentaje o monto manual).
5. **Validaciones de integridad:** una cuenta ya saldada no puede volver a cobrarse;
   las sesiones se bloquean con `select_for_update` durante el cobro.

### 3.5 Ticket post-pago

1. Tras el pago, la pantalla del cliente muestra **"Cuenta pagada"** con su ticket
   y la opción de **"Seguir viendo"** sus pedidos o **"Salir"**.
   - **Pago individual** → solo el cliente que pagó ve el ticket.
   - **Pago total de mesa** → **todos** los clientes de la mesa lo ven.
2. El ticket desglosa productos, **descuentos por promoción**, propina y total,
   con el método de pago utilizado.
3. La `SolicitudPago` registra **qué sesiones cubrió**, de modo que el ticket
   reconstruye solo los pedidos de esa visita (no el histórico de la mesa).
4. Los demás clientes pueden seguir consultando sus pedidos, pero **no pueden
   volver a pedir la cuenta** ni modificar el carrito de una sesión ya pagada.

### 3.6 Reportes (gerente)

El gerente accede a dashboards con gráficas (Chart.js) de ventas por día/semana/mes,
productos más vendidos, cancelaciones, métodos de pago, etc. Puede **exportar a PDF**
un reporte personalizado eligiendo rango de fechas y secciones.

---

## 4. Módulos principales

### 4.1 Cliente (`apps/cliente`)

| Pantalla | Descripción |
|----------|-------------|
| **Bienvenida** | Entrada por QR. Crear sesión nueva o recuperar con alias + PIN. |
| **Menú** | Productos por categoría, modal de producto con modificadores, carrusel de promociones activas (filtradas por día). |
| **Carrito** | Lista de ítems, selector de promoción, preview del descuento, confirmación con token de idempotencia. |
| **Pedidos** | Seguimiento en tiempo real (polling) del estado de cada pedido; solicitud de cuenta; modal de "Cuenta pagada". |

Identidad sin login: cookie `mm_session` → `request.sesion_cliente` (middleware).

### 4.2 Mesero (`apps/mesero`)

| Pantalla | Descripción |
|----------|-------------|
| **Mapa de mesas** | Grid de mesas en tiempo real (polling cada 3 s) con estado visual: libre / ocupada / en cocina / listo / atención. |
| **Detalle de mesa** | Panel lateral con pestañas: sesiones, pedidos, solicitudes de cobro. |
| **Pedido asistido** | El mesero arma un pedido en nombre de una sesión (con selector de promoción). |
| **Cobro** | Modal de pago: efectivo / tarjeta / mixto, propina, cálculo de cambio. Total recalculado en vivo. |
| **Ticket** | Vista HTML del ticket y descarga en PDF. |

### 4.3 Cocina (`apps/cocina`)

| Elemento | Descripción |
|----------|-------------|
| **KDS** | Dos columnas: pendientes y listos. Filtrado por área (`?area=cocina` o `?area=bar`). |
| **Estado por ítem** | Cada `DetallePedido` tiene su flag `listo`; el pedido global solo pasa a `listo` cuando todos sus ítems lo están. |
| **Semáforo** | Colorea los tickets según minutos transcurridos. Umbrales configurables por el gerente. |
| **Polling** | Refresco automático cada 3 s, con anti-solapamiento y pausa cuando la pestaña está oculta. |

### 4.4 Gerente (`apps/gerente`)

| Sección | Descripción |
|---------|-------------|
| **Floor plan** | Mapa de mesas en tiempo real (versión del gerente). |
| **Gestión de menú** | CRUD de productos, categorías, modificadores y promociones. Gestor de imágenes con drag-and-drop, recorte (Cropper.js) y galería. |
| **Mesas** | CRUD de mesas y ubicaciones; generación/descarga de QR. |
| **Empleados** | CRUD de empleados y activación/desactivación. |
| **Reportes** | Dashboards con gráficas; exportación a PDF de reportes personalizados. |
| **Configuración** | Umbrales del semáforo KDS, modo mantenimiento, datos del restaurante (para el ticket), credenciales de PayPal. |
| **Auditoría** | Registro de acciones sensibles. |

---

## 5. Modelo de datos

### Entidades principales y relaciones

```
                          ┌──────────────┐
                          │   Empleado   │  (accounts) — usuario del staff, con rol
                          └──────┬───────┘
                                 │ id_mesero_asignado (SET_NULL)
                                 │
   ┌───────────────┐      ┌──────▼───────┐      ┌────────────────┐
   │ UbicacionMesa │◄─────│     Mesa     │      │ ModalidadIngreso│ (catalogs)
   └───────────────┘ SET  └──────┬───────┘      └────────┬───────┘
                       NULL      │ PROTECT               │ PROTECT
                                 │                       │
                          ┌──────▼───────────────────────▼──┐
                          │         SesionCliente            │  (mesas)
                          │  alias · token_cookie · estado   │
                          └──────┬───────────────────┬──────┘
                                 │ PROTECT           │ SET_NULL
                                 │                   │
                          ┌──────▼───────┐    ┌──────▼─────────┐
                          │    Pedido    │    │  AlertaMesero  │ (mesas)
                          │ estado·token │    └────────────────┘
                          └──────┬───────┘
                                 │ CASCADE
                          ┌──────▼────────┐         ┌──────────────┐
                          │ DetallePedido │────────►│  Producto    │ (menu)
                          │ subtotal·listo│ PROTECT └──────┬───────┘
                          └──────┬────────┘                │
                                 │ CASCADE                 │
                          ┌──────▼────────────┐     ┌──────▼────────┐
                          │ DetalleModificador│     │  Categoria    │ (menu)
                          └───────────────────┘     └───────────────┘
                                 ▲
                                 │ PROTECT
                          ┌──────┴──────────┐
                          │ OpcionModificador│──► GrupoModificador (menu)
                          └─────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │                       SolicitudPago  (pedidos)               │
   │  tipo (individual/grupal) · total_individual · total_mesa     │
   │  propina_sugerida · metodo_pago · estado_solicitud            │
   │  sesion (SET_NULL) · mesa (SET_NULL)                          │
   │  sesiones_cubiertas  ── M2M ──►  SesionCliente                │
   └──────────────────────────────────────────────────────────────┘

   Promocion (menu) ── M2M ──► Producto        (productos_aplicables)
   Promocion ── FK ──► TipoDescuento           (porcentaje, 2x1, combo, …)
   Auditoria (auditoria) ── FK ──► Empleado / Mesa / Pedido / SolicitudPago
   Configuracion (gerente) — pares clave/valor de configuración global
```

### Resumen de entidades

| Entidad | App | Rol |
|---------|-----|-----|
| `Empleado` | accounts | Usuario del staff con `rol`. |
| `ModalidadIngreso`, `MetodoPago`, `EstadoSolicitud` | catalogs | Catálogos auxiliares. |
| `Mesa`, `UbicacionMesa` | mesas | Mesa física y su agrupación. Genera el QR. |
| `SesionCliente` | mesas | Grupo de clientes en una mesa (identidad por cookie). |
| `AlertaMesero` | mesas | Llamada de atención generada por el cliente. |
| `Categoria`, `Producto` | menu | Catálogo del menú; `Categoria.area` define el KDS. |
| `GrupoModificador`, `OpcionModificador` | menu | Opciones (tamaño, leche, etc.). |
| `Promocion`, `TipoDescuento` | menu | Promociones y su tipo de descuento. |
| `Pedido` | pedidos | Comanda; `estado`, `token_idempotencia`. |
| `DetallePedido` | pedidos | Línea de pedido; `subtotal_calculado`, `listo`. |
| `DetalleModificador` | pedidos | Modificador aplicado a una línea (snapshot histórico). |
| `SolicitudPago` | pedidos | Cobro; `tipo`, totales, `sesiones_cubiertas` (M2M). |
| `Auditoria` | auditoria | Bitácora de acciones sensibles. |
| `Configuracion` | gerente | Configuración global (clave/valor). |

### Estados clave

- **`Mesa.estado`**: `libre` → `ocupada` → `libre`.
- **`SesionCliente.estado`**: `activa` → `pagada` → `cerrada`.
- **`Pedido.estado`**: `recibido` → `preparando` → `listo` → `entregado` (o `cancelado`).
- **`DetallePedido.listo`**: `False` → `True` cuando el área correspondiente lo termina.

---

## 6. Guía de instalación y ejecución

### 6.1 Requisitos

- **Docker** y **Docker Compose** instalados.
- Un archivo **`.env`** en la raíz del proyecto con las variables de entorno
  (la base de datos y Django las leen desde ahí). Variables principales:

  ```env
  # Base de datos MariaDB
  MYSQL_DATABASE=mochi_matcha
  MYSQL_USER=mochi
  MYSQL_PASSWORD=tu_password
  MYSQL_ROOT_PASSWORD=tu_root_password
  MYSQL_HOST=db
  MYSQL_PORT=3306

  # Django
  SECRET_KEY=una_clave_secreta_larga
  DEBUG=True
  ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
  SITE_BASE_URL=http://localhost:8000
  ```

### 6.2 Levantar el proyecto

```bash
# 1. Construir e iniciar los contenedores (web + db)
docker compose up -d

# 2. Aplicar las migraciones de la base de datos
docker compose exec web python manage.py migrate

# 3. (Opcional) Crear un superusuario para el admin de Django
docker compose exec web python manage.py createsuperuser
```

La aplicación queda disponible en **http://localhost:8000**.

### 6.3 Ejecutar el seed (datos de demostración)

El script `seed.py` puebla la base con catálogos, empleados, mesas, menú,
promociones y un histórico de pedidos.

```bash
docker compose exec web python manage.py shell -c "exec(open('seed.py').read())"
```

> ⚠️ El seed **elimina** los pedidos, sesiones y solicitudes de pago previos.
> Los productos, categorías, empleados y modificadores se conservan o actualizan.

**Credenciales de ejemplo creadas por el seed:**

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| `admin` | `admin1234` | Administrador |
| `gerente1` | `gerente123` | Gerente |
| `maria`, `carlos` | `mesero123` | Mesero |
| `lucia`, `roberto` | `cocina123` | Cocina |

### 6.4 Comandos útiles

```bash
# Ver logs del contenedor web
docker compose logs -f web

# Reiniciar solo el contenedor web (tras cambiar settings)
docker compose restart web

# Abrir una shell de Django
docker compose exec web python manage.py shell

# Verificar el proyecto
docker compose exec web python manage.py check
```

---

## 7. Guía de uso rápido

### Probar el flujo del **cliente**

1. Inicia sesión como gerente y entra a **Gestión de Menú → Mesas**; abre el QR de
   una mesa o copia su URL (`/bienvenida/?mesa=<id>`).
2. Abre esa URL en otra ventana/incógnito → elige "Soy nuevo" → ingresa un alias.
3. Anota el **PIN** que aparece (si eres el primer cliente).
4. Navega el menú, agrega productos al carrito, confirma el pedido.
5. Ve a "Mis pedidos" para ver el seguimiento en tiempo real.

### Probar el flujo del **mesero**

1. Entra a `http://localhost:8000/mesero/login/` con `maria` / `mesero123`.
2. En el **mapa de mesas**, haz clic en la mesa ocupada → panel lateral.
3. Prueba un **pedido asistido**: pestaña correspondiente → agrega productos → enviar.
4. Cuando el cliente pida la cuenta, aparecerá la solicitud → **"Ir a cobrar"** →
   elige método, propina → confirma.

### Probar el flujo de **cocina**

1. Entra a `http://localhost:8000/cocina/login/` con `lucia` / `cocina123`.
2. Verás el **KDS** con los pedidos pendientes del área **cocina**.
3. Cambia a **bar** con las pestañas superiores.
4. Pulsa "Comenzar preparación" y luego "Marcar como listo" en un ticket.
5. Observa cómo un pedido mixto permanece en preparación hasta que ambas áreas terminan.

### Probar el flujo del **gerente**

1. Entra a `http://localhost:8000/gerente/login/` con `gerente1` / `gerente123`.
2. Explora **Floor Plan**, **Gestión de Menú**, **Reportes** y **Configuración**.
3. En Reportes, prueba la **exportación a PDF** con rango de fechas.

---

## 8. API de endpoints (principales)

> Todas las rutas del staff requieren autenticación con el rol correspondiente.
> Las rutas del cliente usan la cookie `mm_session`.

### Cliente (`/` raíz)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/bienvenida/?mesa=<id>` | Pantalla de entrada por QR. |
| POST | `/bienvenida/crear/<mesa_id>/` | Crea una nueva `SesionCliente`. |
| POST | `/bienvenida/recuperar/<mesa_id>/` | Recupera sesión con alias + PIN. |
| GET | `/menu/` | Menú con categorías y promociones. |
| GET | `/carrito/` | Carrito actual. |
| POST | `/carrito/agregar/`·`/actualizar/`·`/eliminar/`·`/limpiar/` | Operaciones de carrito. |
| POST | `/carrito/calcular/` | Recalcula descuentos (preview). |
| POST | `/carrito/confirmar/` | Confirma el pedido (idempotente). |
| GET | `/pedidos/` · `/pedidos/estado/` | Seguimiento de pedidos (polling). |
| POST | `/pedidos/cuenta/` | Solicita la cuenta (individual o grupal). |
| GET | `/sesion/estado/` | Polling del estado de la sesión (detecta pago). |
| POST | `/sesion/cerrar/` | Cierre voluntario de la sesión tras pagar. |
| POST | `/pago/paypal/crear/` · `/pago/paypal/capturar/` | Pago en línea con PayPal. |

### Mesero (`/mesero/`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/mesero/login/` · `/mesero/logout/` | Autenticación. |
| GET | `/mesero/mapa/` · `/mesero/mapa/estado/` | Mapa de mesas (HTML + polling JSON). |
| GET | `/mesero/mapa/<mesa_id>/` | Detalle de mesa (JSON). |
| POST | `/mesero/pedidos/entregar/` · `/cancelar/` | Gestión de pedidos. |
| POST | `/mesero/asistido/confirmar/` | Confirma un pedido asistido. |
| GET/POST | `/mesero/pago/` · `/mesero/pago/procesar/` | Cobro. |
| GET | `/mesero/pago/total/` | Total recalculado en vivo. |
| POST | `/mesero/paypal/crear-orden/` · `/paypal/capturar/` | PayPal del mesero. |
| GET | `/mesero/ticket/<id>/` · `/ticket/<id>/pdf/` | Ticket HTML y PDF. |
| GET | `/mesero/productos/json/` | Catálogo de productos (para el modal asistido). |

### Cocina (`/cocina/`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/cocina/login/` · `/cocina/logout/` | Autenticación. |
| GET | `/cocina/kds/?area=<cocina\|bar>` | Pantalla del KDS. |
| GET | `/cocina/pedidos-json/?area=<...>` | Polling de pedidos del KDS. |
| POST | `/cocina/marcar-listo/` | Avanza un pedido por área. |

### Gerente (`/gerente/`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/gerente/login/` · `/gerente/logout/` | Autenticación. |
| GET | `/gerente/floor-plan/` · `/floor-plan/estado/` | Mapa de mesas. |
| GET/POST | `/gerente/menu/productos/...` | CRUD de productos. |
| GET/POST | `/gerente/menu/categorias/...` | CRUD de categorías (crear/editar/eliminar). |
| GET/POST | `/gerente/menu/modificadores/...` | CRUD de modificadores. |
| GET/POST | `/gerente/menu/promociones/...` | CRUD de promociones. |
| GET/POST | `/gerente/mesas/...` | CRUD de mesas y ubicaciones. |
| GET/POST | `/gerente/empleados/...` | CRUD de empleados. |
| GET | `/gerente/reportes/` · `/reportes/avanzados/` | Dashboards de reportes. |
| GET | `/gerente/reportes/exportar-custom/` | Exportación de reporte personalizado a PDF. |
| GET/POST | `/gerente/configuracion/` | Configuración del sistema. |
| POST | `/gerente/upload-imagen/` · `/imagenes/listar/` · `/imagenes/eliminar/` | Gestor de imágenes. |
| GET | `/gerente/auditoria/` | Bitácora de auditoría. |

---

## 9. Solución de problemas comunes

| Problema | Causa probable | Solución |
|----------|----------------|----------|
| **Error 500 al guardar configuración** o al guardar texto con emojis | La conexión a MariaDB no usa `utf8mb4`. | Verifica que `config/settings.py` tenga `OPTIONS: {'charset': 'utf8mb4'}` y reinicia el contenedor `web`. |
| **`Table '...' doesn't exist`** | Migraciones sin aplicar. | `docker compose exec web python manage.py migrate`. |
| **El QR apunta a `localhost`** en producción | `SITE_BASE_URL` apunta a localhost y no se generó el QR con el dominio del request. | El sistema usa `request.build_absolute_uri` para generar el QR; asegúrate de que el proxy reenvía el `Host` correcto y que `ALLOWED_HOSTS` lo incluye. |
| **El cliente es "expulsado" tras el pago** | Middleware del cliente no reconoce la sesión `pagada`. | El middleware ya carga sesiones `activa` y `pagada`; si se modificó, restaurar ese comportamiento. |
| **Pedido duplicado por doble-click** | Falta el token de idempotencia. | El frontend genera un `idempotency_key` por intento; el backend lo valida contra `Pedido.token_idempotencia`. |
| **El KDS no toma los nuevos umbrales del semáforo** | Caché viejo en `localStorage`. | El KDS ahora toma los umbrales del servidor en cada carga; basta recargar la página. |
| **`docker compose` dice "Docker Desktop is paused/stopped"** | Docker Desktop no está corriendo. | Inicia Docker Desktop y vuelve a ejecutar `docker compose up -d`. |
| **PayPal devuelve 503 "no disponible"** | Faltan credenciales de PayPal. | Configura `paypal_client_id` y `paypal_secret` en **Configuración** (panel del gerente). |
| **El seed falla con `ProtectedError`** | Hay pedidos que referencian sesiones por FK protegida. | El seed limpia en orden (`SolicitudPago` → `DetalleModificador` → `DetallePedido` → `Pedido` → `SesionCliente`); si falla, revisa que no haya procesos creando pedidos en paralelo. |
| **Cambios en `settings.py` no se reflejan** | El contenedor cachea la configuración. | `docker compose restart web`. |

---

## 10. Notas de mantenimiento

- **Migraciones:** tras modificar cualquier modelo, generar con
  `docker compose exec web python manage.py makemigrations` y aplicar con `migrate`.
- **Idempotencia y concurrencia:** los flujos críticos (confirmar pedido, cobrar,
  crear sesión) usan `transaction.atomic()` + `select_for_update()` para evitar
  duplicados y condiciones de carrera.
- **Promociones:** la regla de negocio es **una sola promoción por pedido**. El
  motor está centralizado en `apps/pedidos/utils.py` (`aplicar_promociones`).
- **Imágenes:** se guardan en `media/images/`; en la base de datos solo se
  almacena la ruta relativa, nunca el binario.
- **Comentarios del código:** todos los archivos fuente (Python, plantillas, JS y
  CSS) están comentados — docstrings de módulo/función y comentarios de sección en
  las plantillas. Los comentarios marcados con `BUGFIX`, `FIX`, `Pn` o `En` documentan
  correcciones de errores y puntos débiles detectados durante el desarrollo.
