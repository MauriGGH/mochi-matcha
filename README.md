<div align="center">

# Mochi Matcha — POS

<p>
  <img src="https://img.shields.io/badge/Django-5.0.2-092E20?style=flat&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Bootstrap-5-7952B3?style=flat&logo=bootstrap&logoColor=white" alt="Bootstrap">
  <img src="https://img.shields.io/badge/MariaDB-10.6-003545?style=flat&logo=mariadb&logoColor=white" alt="MariaDB">
  <img src="https://img.shields.io/badge/JavaScript-ES6-F7DF1E?style=flat&logo=javascript&logoColor=black" alt="JavaScript">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Licencia-MIT-green?style=flat" alt="MIT License">
</p>

Sistema de punto de venta (POS) para restaurante, desarrollado en Django. Cubre el ciclo completo de operacion: el cliente escanea un QR en la mesa, ordena desde su dispositivo, cocina/bar recibe los pedidos en un KDS, el mesero gestiona mesas y cobros, y el gerente administra el catalogo, empleados y reportes.

</div>

---

## Instalacion rapida

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd mochi-matcha

# 2. Crear el archivo de variables de entorno
cp env.example .env
```

Editar `.env` con los valores del entorno de desarrollo:

```env
# Base de datos
MYSQL_ROOT_PASSWORD=root
MYSQL_DATABASE=mochi_matcha
MYSQL_USER=mochi
MYSQL_PASSWORD=mochi_pass
MYSQL_HOST=db
MYSQL_PORT=3306

# Django
SECRET_KEY=django-insecure-dev-key-cambiar-en-produccion
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
```

```bash
# 3. Levantar los contenedores
docker compose up -d --build

# 4. Aplicar migraciones
docker exec mochi_matcha_web python manage.py migrate

# 5. Cargar datos de prueba
docker exec -it mochi_matcha_web python seed.py

# 6. Acceder a la aplicacion
#    http://localhost:8000
```

> Para instrucciones de despliegue en produccion (Nginx, Gunicorn, SSL), consultar la documentacion completa.

---

## Caracteristicas principales

| Modulo | Funcionalidad |
|--------|--------------|
| **Cliente** | Acceso por QR, creacion/recuperacion de sesion con PIN, menu digital, carrito con modificadores y promociones, seguimiento de pedidos, solicitud de cuenta y ayuda |
| **Mesero** | Mapa de mesas con estado en tiempo real (polling), pedidos asistidos, entrega y cancelacion de pedidos, gestion de alertas, proceso de pago individual y grupal |
| **Cocina / Bar** | Kitchen Display System (KDS) con actualizacion cada 3 s, filtrado por area (cocina / bar), marcado de items como listos |
| **Gerente** | Dashboard operacional, floor plan, CRUD de productos/categorias/modificadores/promociones, gestion de mesas y empleados, reportes, log de auditoria, configuracion del sistema |
| **QR por mesa** | Cada mesa tiene un codigo QR unico generado automaticamente que lleva al cliente directamente a su sesion |
| **Sesiones con PIN** | El cliente crea una sesion, obtiene su PIN y puede recuperarla desde otro dispositivo en la misma mesa |
| **Modificadores** | Grupos de opciones (unica / multiple) configurables por producto con precio extra y snapshots historicos |
| **Promociones** | Descuentos por porcentaje, monto fijo, 2x1, combo precio fijo y "lleva X paga Y"; aplicables por item o sobre el total del carrito |
| **Auditoria** | Registro inmutable de acciones criticas: pagos, cancelaciones y cierres de mesa |

---

## Arquitectura del sistema

```
                         [ Navegador / Dispositivo ]
                                     |
              ┌──────────────────────┼──────────────────────┐
              |                      |                      |
         [Cliente]             [Mesero / KDS]          [Gerente]
         QR → sesion           login por rol           login por rol
         menu / carrito        mapa de mesas           dashboard
         pedidos propios       alertas / cobros        CRUD / reportes
              |                      |                      |
              └──────────────────────┼──────────────────────┘
                                     |
                            [ Django 5 / WSGI ]
                                     |
                    ┌────────────────┼────────────────┐
                    |                |                |
              apps/cliente    apps/mesero       apps/gerente
              apps/cocina     apps/pedidos      apps/auditoria
              apps/mesas      apps/menu         apps/accounts
                    |                |                |
                    └────────────────┼────────────────┘
                                     |
                          [ MariaDB 10.6 (Docker) ]
```

> La comunicacion en tiempo real se implementa mediante **polling HTTP cada 3 segundos** desde el frontend (KDS y mapa de mesas). No se utilizan WebSockets.

---

## Modulos

<details>
<summary><strong>Cliente</strong> — Experiencia de mesa</summary>

El modulo cliente es la interfaz publica accesible desde el QR de cada mesa. No requiere autenticacion de empleado; la identidad del comensal se gestiona mediante una sesion anonima con alias y PIN.

**Flujo principal:**

1. El cliente escanea el QR de su mesa y accede a `/bienvenida/`.
2. Crea una sesion eligiendo un alias (o recupera una sesion existente con su PIN).
3. Navega por el menu, agrega productos al carrito con sus modificadores.
4. Confirma el pedido; este pasa al KDS de cocina/bar.
5. Monitorea el estado de sus pedidos en `/pedidos/`.
6. Solicita la cuenta o ayuda del mesero cuando lo necesita.

**Vistas principales:** `bienvenida`, `crear_sesion`, `recuperar_sesion`, `menu`, `carrito`, `confirmar_pedido`, `pedidos`, `solicitar_cuenta`, `solicitar_ayuda`

**Middleware:** `ClienteSessionMiddleware` carga automaticamente la sesion activa (o pagada) del cliente en cada request.

</details>

<details>
<summary><strong>Mesero</strong> — Gestion de sala</summary>

Interfaz de uso exclusivo del personal de sala. Requiere autenticacion con rol `mesero`.

**Funcionalidades:**

- Mapa de mesas con estado en tiempo real (libre / ocupada) mediante polling.
- Vista de detalle por mesa: sesiones activas, pedidos y total acumulado.
- Pedidos asistidos: el mesero puede ordenar directamente en nombre del cliente.
- Gestion de alertas: ayuda solicitada por clientes y solicitudes de cuenta.
- Flujo de pago: individual (por sesion) o grupal (toda la mesa), seleccion de metodo de pago.
- Cancelacion de pedidos con motivo.
- Cierre de mesa al finalizar el servicio.

**Vistas principales:** `mapa_mesas`, `detalle_mesa`, `pedido_asistido`, `alertas`, `cuentas`, `pago`, `procesar_pago`, `cerrar_mesa`

</details>

<details>
<summary><strong>Cocina / Bar</strong> — Kitchen Display System</summary>

Pantalla de produccion para el personal de cocina y bar. Requiere autenticacion con rol `cocina`.

**Funcionalidades:**

- KDS con lista de pedidos pendientes y en preparacion.
- Filtrado automatico por area: un usuario de cocina ve solo items de categoria `cocina`; uno de bar ve solo items de categoria `bar`.
- Actualizacion automatica cada 3 segundos via endpoint `/cocina/pedidos-json/`.
- Marcado de items como listos con un solo click.

**Vistas principales:** `kds`, `pedidos_json`, `marcar_listo`

</details>

<details>
<summary><strong>Gerente</strong> — Administracion y reportes</summary>

Panel completo de administracion. Requiere autenticacion con rol `gerente` o `admin`.

**Funcionalidades:**

- **Dashboard:** resumen operacional del dia con estadisticas en tiempo real.
- **Floor plan:** vista de sala con estado de mesas y acceso rapido a detalles.
- **Catalogo de menu:** CRUD de productos, categorias (con asignacion de area cocina/bar), grupos de modificadores (con soporte de plantillas reutilizables) y promociones.
- **Gestion de mesas:** CRUD de mesas y ubicaciones, asignacion de mesero por mesa.
- **Empleados:** alta, baja logica (toggle activo) y edicion de personal por rol.
- **Reportes:** filtrado por rango de fechas, reportes quincenales y exportacion.
- **Auditoria:** log de acciones criticas con filtros.
- **Configuracion:** pares clave-valor para parametros globales del sistema.

**Vistas principales:** `dashboard`, `floor_plan`, `productos`, `categorias`, `modificadores`, `promociones`, `mesas`, `empleados`, `reportes`, `auditoria`, `configuracion`

</details>

---

## Rutas para testing manual

### Publicas

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/` | Redirige a `/bienvenida/` |
| GET | `/bienvenida/` | Pantalla de bienvenida de mesa |
| GET | `/mantenimiento/` | Pagina de mantenimiento |
| GET | `/admin/` | Django Admin |
| GET/POST | `/accounts/login/` | Login generico |

### Cliente

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| POST | `/bienvenida/crear/<mesa_id>/` | Crear sesion de cliente |
| POST | `/bienvenida/recuperar/<mesa_id>/` | Recuperar sesion con PIN |
| GET | `/bienvenida/pin/` | Mostrar PIN generado |
| GET | `/bienvenida/estado/<mesa_id>/` | Estado actual de la mesa |
| GET | `/menu/` | Menu digital |
| GET | `/carrito/` | Ver carrito |
| POST | `/carrito/agregar/` | Agregar producto al carrito |
| POST | `/carrito/actualizar/` | Cambiar cantidad de un item |
| POST | `/carrito/eliminar/` | Eliminar item del carrito |
| POST | `/carrito/limpiar/` | Vaciar carrito |
| POST | `/carrito/confirmar/` | Confirmar pedido |
| POST | `/carrito/calcular/` | Calcular totales y promociones |
| GET | `/pedidos/` | Mis pedidos |
| GET | `/pedidos/estado/` | Estado de pedidos (polling) |
| POST | `/pedidos/ayuda/` | Solicitar ayuda al mesero |
| POST | `/pedidos/cuenta/` | Solicitar la cuenta |

### Mesero

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET/POST | `/mesero/login/` | Login mesero |
| GET | `/mesero/logout/` | Logout |
| GET | `/mesero/mapa/` | Mapa de mesas |
| GET | `/mesero/mapa/estado/` | Estado de mesas (polling JSON) |
| GET | `/mesero/mapa/<mesa_id>/` | Detalle de mesa |
| GET | `/mesero/pedidos-listos/` | Pedidos listos para entregar |
| POST | `/mesero/pedidos/entregar/` | Marcar pedido como entregado |
| POST | `/mesero/pedidos/cancelar/` | Cancelar pedido |
| GET/POST | `/mesero/pedidos/<id>/editar/` | Editar pedido |
| GET | `/mesero/alertas/` | Ver alertas activas |
| POST | `/mesero/alertas/atender/` | Marcar alerta como atendida |
| GET | `/mesero/cuentas/` | Solicitudes de pago pendientes |
| POST | `/mesero/cuentas/solicitar/` | Emitir solicitud de pago |
| POST | `/mesero/cuentas/cancelar/` | Cancelar solicitud de pago |
| GET/POST | `/mesero/asistido/` | Crear pedido asistido |
| POST | `/mesero/asistido/confirmar/` | Confirmar pedido asistido |
| POST | `/mesero/sesion/agregar/` | Agregar sesion asistida a mesa |
| POST | `/mesero/sesion/cerrar/` | Cerrar sesion de cliente |
| POST | `/mesero/mesa/cerrar/` | Cerrar mesa |
| GET | `/mesero/pago/` | Pantalla de pago |
| POST | `/mesero/pago/procesar/` | Procesar pago |
| GET | `/mesero/productos/json/` | Catalogo de productos (JSON) |

### Cocina

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET/POST | `/cocina/login/` | Login cocina/bar |
| GET | `/cocina/logout/` | Logout |
| GET | `/cocina/kds/` | Kitchen Display System |
| GET | `/cocina/pedidos-json/` | Pedidos activos (polling JSON) |
| POST | `/cocina/marcar-listo/` | Marcar item como listo |

### Gerente

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET/POST | `/gerente/login/` | Login gerente |
| GET | `/gerente/logout/` | Logout |
| GET | `/gerente/dashboard/` | Dashboard operacional |
| GET | `/gerente/floor-plan/` | Vista de sala |
| GET | `/gerente/floor-plan/estado/` | Estado de mesas (JSON) |
| GET | `/gerente/floor-plan/mesa/<id>/` | Detalle de mesa |
| GET/POST | `/gerente/menu/productos/` | Listado y creacion de productos |
| GET/POST | `/gerente/menu/productos/<id>/editar/` | Editar producto |
| POST | `/gerente/menu/productos/<id>/eliminar/` | Eliminar producto |
| GET/POST | `/gerente/menu/categorias/` | Gestion de categorias |
| POST | `/gerente/menu/categorias/<id>/eliminar/` | Eliminar categoria |
| GET/POST | `/gerente/menu/modificadores/` | Gestion de modificadores |
| POST | `/gerente/menu/modificadores/crear/` | Crear modificador |
| POST | `/gerente/menu/modificadores/clonar/` | Clonar plantilla |
| GET/POST | `/gerente/menu/modificadores/<id>/editar/` | Editar modificador |
| POST | `/gerente/menu/modificadores/<id>/eliminar/` | Eliminar modificador |
| POST | `/gerente/menu/modificadores/<id>/plantilla/` | Toggle plantilla reutilizable |
| GET/POST | `/gerente/menu/promociones/` | Gestion de promociones |
| POST | `/gerente/menu/promociones/<id>/toggle/` | Activar/desactivar promocion |
| GET/POST | `/gerente/menu/promociones/<id>/editar/` | Editar promocion |
| POST | `/gerente/menu/promociones/<id>/eliminar/` | Eliminar promocion |
| GET/POST | `/gerente/mesas/` | Gestion de mesas |
| POST | `/gerente/mesas/crud/` | CRUD de mesas |
| POST | `/gerente/mesas/ubicacion/crear/` | Crear ubicacion |
| POST | `/gerente/mesas/ubicacion/<id>/editar/` | Editar ubicacion |
| POST | `/gerente/mesas/ubicacion/<id>/eliminar/` | Eliminar ubicacion |
| POST | `/gerente/mesas/<id>/eliminar/` | Eliminar mesa |
| POST | `/gerente/mesas/<id>/asignar/` | Asignar mesero a mesa |
| GET/POST | `/gerente/empleados/` | Listado de empleados |
| POST | `/gerente/empleados/nuevo/` | Crear empleado |
| POST | `/gerente/empleados/<id>/toggle/` | Activar/desactivar empleado |
| GET/POST | `/gerente/empleados/<id>/editar/` | Editar empleado |
| GET | `/gerente/reportes/` | Reportes por fecha |
| GET | `/gerente/reportes/exportar/` | Exportar reporte |
| GET | `/gerente/reportes/quincenales/` | Reportes quincenales |
| GET | `/gerente/auditoria/` | Log de auditoria |
| GET | `/gerente/stats/` | Estadisticas JSON (dashboard) |
| GET/POST | `/gerente/configuracion/` | Configuracion del sistema |

---

## Modelo de datos

| Entidad | App | Descripcion |
|---------|-----|-------------|
| `Empleado` | accounts | Usuario del sistema. Roles: `mesero`, `cocina`, `gerente`, `admin`. Extiende `AbstractBaseUser`. |
| `UbicacionMesa` | mesas | Zona o area de la sala (ej. TERRAZA, INTERIOR). |
| `Mesa` | mesas | Mesa fisica con numero, capacidad, QR unico y PIN temporal. |
| `SesionCliente` | mesas | Sesion anonima de un comensal en una mesa. Estados: `activa`, `pagada`, `cerrada`. |
| `AlertaMesero` | mesas | Alerta generada por el cliente: ayuda, solicitud de cuenta o personalizada. |
| `Categoria` | menu | Categoria de producto con asignacion de area (`cocina`, `bar`, `ambos`). |
| `Producto` | menu | Item del menu con precio, disponibilidad y URL de imagen. |
| `GrupoModificador` | menu | Grupo de opciones personalizables de un producto (ej. "Tamano", "Leche"). Soporta plantillas reutilizables. |
| `OpcionModificador` | menu | Opcion concreta dentro de un grupo con precio extra opcional. |
| `Promocion` | menu | Descuento configurable: porcentaje, monto fijo, 2x1, combo o "lleva X paga Y". |
| `Pedido` | pedidos | Orden completa de una sesion. Estados: `recibido`, `preparando`, `listo`, `entregado`, `cancelado`. |
| `DetallePedido` | pedidos | Linea de un pedido: producto, cantidad, subtotal y promocion aplicada. |
| `DetalleModificador` | pedidos | Modificador aplicado a un detalle; conserva snapshot historico del nombre de la opcion. |
| `SolicitudPago` | pedidos | Solicitud de cobro individual o grupal con metodo de pago y propina sugerida. |
| `MetodoPago` | catalogs | Catalogo de metodos de pago (efectivo, tarjeta, mixto). |
| `ModalidadIngreso` | catalogs | Catalogo de formas de ingreso (QR, asistido por mesero). |
| `EstadoSolicitud` | catalogs | Catalogo de estados de una solicitud de pago (pendiente, procesada, cancelada). |
| `Configuracion` | gerente | Pares clave-valor para parametros globales del sistema. |
| `Auditoria` | auditoria | Registro de acciones criticas con referencia a empleado, mesa, pedido o solicitud de pago. |

---

## Tecnologias utilizadas

| Tecnologia | Version | Uso |
|-----------|---------|-----|
| Python | 3.11 | Lenguaje base |
| Django | 5.0.2 | Framework web |
| MariaDB | 10.6 | Base de datos relacional |
| mysqlclient | 2.2.4 | Conector Django-MariaDB |
| Bootstrap | 5 | Componentes UI y sistema de grilla |
| Bootstrap Icons | 1.11.3 | Iconografia (CDN) |
| JavaScript | ES6 | Interactividad y polling frontend |
| Docker | — | Contenedorizacion del entorno de desarrollo |
| Docker Compose | — | Orquestacion de servicios (web + db) |
| qrcode[pil] | 7.4.2 | Generacion de codigos QR para mesas |
| python-decouple | 3.8 | Gestion de variables de entorno |

---

## Estructura del proyecto

```
mochi-matcha/
├── apps/
│   ├── accounts/          # Autenticacion y modelo Empleado
│   ├── auditoria/         # Log de acciones criticas
│   ├── catalogs/          # Catalogos auxiliares (MetodoPago, ModalidadIngreso, EstadoSolicitud)
│   ├── cliente/           # Modulo cliente: menu, carrito, sesiones, pedidos
│   │   └── middleware.py  # ClienteSessionMiddleware
│   ├── cocina/            # KDS (Kitchen Display System)
│   ├── gerente/           # Dashboard, CRUD, reportes, configuracion
│   ├── menu/              # Productos, categorias, modificadores, promociones
│   ├── mesas/             # Mesas, sesiones de cliente, alertas de mesero
│   ├── mesero/            # Mapa de mesas, pedidos asistidos, cobros
│   └── pedidos/           # Pedidos, detalles, modificadores aplicados, solicitudes de pago
│       └── utils.py       # Logica de promociones
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── static/
│   └── css/
│       ├── cliente.css
│       ├── mochi.css
│       └── staff.css
├── templates/
│   ├── base/
│   │   ├── cliente_base.html
│   │   ├── staff_base.html
│   │   └── login.html
│   └── mantenimiento.html
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── requirements.txt
├── seed.py
└── env.example
```

---

<div align="center">

Mochi Matcha &nbsp;&middot;&nbsp; bi-cup-hot

</div>
