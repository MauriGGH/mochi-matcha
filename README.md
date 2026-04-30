<div align="center">

# 🍵 Mochi Matcha

### Sistema de Gestión de Pedidos para Cafetería

*Desde el escaneo del QR hasta el cierre de mesa — todo en un solo sistema.*

<br/>

[![Django](https://img.shields.io/badge/Django_5-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap_5-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![MySQL](https://img.shields.io/badge/MySQL_8-4479A1?style=for-the-badge&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![JavaScript](https://img.shields.io/badge/JavaScript_Vanilla-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/es/docs/Web/JavaScript)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

</div>

---

## ¿Qué es Mochi Matcha?

**Mochi Matcha** es un sistema completo de gestión de pedidos diseñado para cafeterías. Los clientes escanean un código QR desde su móvil, eligen un alias y comienzan a ordenar — sin descargas, sin registros. El pedido viaja directo a la cocina, el mesero lo gestiona desde su panel y el gerente tiene visibilidad total del negocio en tiempo real.

---

## ✨ Características principales

| Característica | Descripción |
|---|---|
| 📲 **Acceso sin registro** | Escanea QR → elige alias → PIN de mesa generado automáticamente |
| 👥 **Sesiones individuales** | Cada comensal en la misma mesa tiene su propio carrito y cuenta |
| 🍽️ **Menú con modificadores** | Opciones personalizables (leche, extras) con precios en tiempo real |
| 🔔 **Pedidos a cocina** | Confirmación automática y visualización FIFO en monitor KDS |
| 🗺️ **Mapa de mesas en vivo** | Estado de cada mesa actualizado cada 3 segundos |
| 💳 **Cobro flexible** | Pago individual o grupal — efectivo, tarjeta o mixto |
| 📊 **Reportes de gestión** | Ventas, afluencia, tiempos de servicio y auditoría de cancelaciones |

---

## 🏗️ Arquitectura

```
      ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
      │ 📱 Cliente │ │ 🧑 Mesero  │ │ 🍳 Cocina  │ │ 💼 Gerente │
      │   (móvil)  │ │  (tablet)  │ │     KDS    │ │   (admin)  │
      └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
            │              │              │              │
            └──────────────┴──────────────┴──────────────┘
                                    │
                        ┌───────────▼───────────┐
                        │       Django 5        │
                        │      (Python 3.11)    │
                        └───────────┬───────────┘
                        
                        ┌───────────▼───────────┐
                        │     MySQL / MariaDB   │
                        └───────────────────────┘
```

**Frontend:** Django Templates + Bootstrap 5 — diseño responsive, polling con JavaScript vanilla  
**Backend:** Django 5 (Python 3.11) — autenticación dual (clientes vía cookie, staff vía sesión Django)  
**Base de datos:** MySQL 8.0 / MariaDB

---

## 📱 Módulos del sistema

<details>
<summary><strong>🧑‍💻 Aplicación Cliente (móvil)</strong></summary>

<br/>

- **Acceso**: QR → alias → PIN generado o recuperación de sesión existente
- **Menú**: Categorías, productos con modificadores y notas especiales
- **Carrito**: Resumen, ajuste de cantidades y envío a cocina
- **Seguimiento**: Estado de pedidos activos en tiempo real
- **Acciones**: Solicitud de ayuda y petición de cuenta al mesero

</details>

<details>
<summary><strong>🧑‍🍳 Panel de Mesero</strong></summary>

<br/>

- **Mapa de mesas**: Vista en tiempo real (libre / ocupada / con pedidos / pagando)
- **Panel de mesa**: PIN visible, sesiones activas, pedidos y solicitudes
- **Pedido asistido**: Modal para agregar productos en nombre de un cliente
- **Procesamiento de pago**: Efectivo / tarjeta / mixto con cálculo de cambio
- **Cierre de mesa**: Libera la mesa e invalida el PIN automáticamente

</details>

<details>
<summary><strong>🍳 Monitor de Cocina — KDS</strong></summary>

<br/>

- **Pedidos pendientes**: Orden FIFO con semáforo de tiempos configurable
- **Botón "Listo"**: Mueve el pedido a la columna de entregados con un solo toque
- **Filtrado por área**: Cocina (alimentos) y bar (bebidas) en vistas separadas

</details>

<details>
<summary><strong>💼 Panel de Gerente</strong></summary>

<br/>

- **Gestión de menú**: CRUD de categorías, productos, modificadores y promociones
- **Gestión de mesas**: Alta, edición, desactivación y generación de QR
- **Gestión de empleados**: Creación de usuarios con roles (mesero / gerente / admin)
- **Reportes**: Ventas por período, productos más vendidos, afluencia, tiempos de servicio, promociones aplicadas y auditoría de cancelaciones
- **Configuración**: Modo mantenimiento y umbrales del semáforo KDS

</details>

---

## 🧪 Rutas para Testing Manual

### 🔓 Públicas (sin login)

| URL | Descripción |
|-----|-------------|
| `/` | Redirige a `/bienvenida/` |
| `/bienvenida/` | Pantalla inicial para ingresar PIN o crear sesión |
| `/bienvenida/crear/<mesa_id>/` | Crear nueva sesión en una mesa |
| `/bienvenida/recuperar/<mesa_id>/` | Recuperar sesión existente con PIN |
| `/bienvenida/pin/` | Muestra el PIN de la sesión actual |
| `/bienvenida/estado/<mesa_id>/` | (JSON) Estado de mesa (incluye PIN y sesiones activas) |
| `/accounts/login/` | Login genérico (staff) |
| `/admin/` | Panel de administración de Django |

### 🧑‍💻 Cliente (móvil)

| URL | Descripción |
|-----|-------------|
| `/menu/` | Menú digital |
| `/carrito/` | Ver carrito actual |
| `/carrito/agregar/` | POST para agregar producto |
| `/carrito/actualizar/` | POST para modificar cantidad |
| `/carrito/eliminar/` | POST para quitar ítem |
| `/carrito/limpiar/` | POST para vaciar carrito |
| `/carrito/confirmar/` | POST para enviar pedido a cocina |
| `/pedidos/` | Ver pedidos activos de la sesión |
| `/pedidos/estado/` | (JSON) Estado de pedidos |
| `/pedidos/ayuda/` | POST para llamar al mesero |
| `/pedidos/cuenta/` | POST para pedir la cuenta |

### 🧑‍🍳 Mesero (requiere login)

| URL | Descripción |
|-----|-------------|
| `/mesero/login/` | Login de mesero |
| `/mesero/logout/` | Cerrar sesión |
| `/mesero/mapa/` | Mapa de mesas (vista principal) |
| `/mesero/mapa/estado/` | (JSON) Estado de todas las mesas |
| `/mesero/mapa/<mesa_id>/` | Detalle de una mesa |
| `/mesero/pedidos-listos/` | Pedidos listos para entregar |
| `/mesero/pedidos/entregar/` | POST para marcar pedido como entregado |
| `/mesero/sesion/cerrar/` | POST para cerrar una sesión de cliente |
| `/mesero/mesa/cerrar/` | POST para cerrar mesa completa |
| `/mesero/asistido/` | Tomar pedido asistido |
| `/mesero/asistido/confirmar/` | POST para confirmar pedido asistido |
| `/mesero/alertas/` | Alertas de ayuda y solicitudes de cuenta |
| `/mesero/cuentas/` | Solicitudes de pago pendientes |
| `/mesero/pago/` | Vista de procesamiento de pago |
| `/mesero/pago/procesar/` | POST para marcar pago como realizado |
| `/mesero/mesas/` | Alias de `/mesero/mapa/` |
| `/mesero/productos/json/` | (JSON) Lista de productos para pedido asistido |

### 🍳 Cocina (requiere login)

| URL | Descripción |
|-----|-------------|
| `/cocina/login/` | Login de cocina |
| `/cocina/logout/` | Cerrar sesión |
| `/cocina/kds/` | Pantalla KDS |
| `/cocina/pedidos-json/` | (JSON) Pedidos pendientes y en preparación |
| `/cocina/marcar-listo/` | POST para marcar pedido como listo |

### 💼 Gerente (requiere login)

| URL | Descripción |
|-----|-------------|
| `/gerente/login/` | Login de gerente |
| `/gerente/logout/` | Cerrar sesión |
| `/gerente/dashboard/` | Panel principal |
| `/gerente/floor-plan/` | Plano de mesas (solo lectura) |
| `/gerente/floor-plan/estado/` | (JSON) Estado de mesas |
| `/gerente/floor-plan/mesa/<mesa_id>/` | Detalle de mesa |
| `/gerente/pedidos/cancelar/` | POST para cancelar un pedido |
| `/gerente/menu/` | Gestión de productos |
| `/gerente/menu/productos/` | (alias) Gestión de productos |
| `/gerente/menu/productos/nuevo/` | Nuevo producto |
| `/gerente/menu/productos/<id>/editar/` | Editar producto |
| `/gerente/menu/productos/<id>/eliminar/` | POST para eliminar producto |
| `/gerente/menu/categorias/` | Gestión de categorías |
| `/gerente/menu/categorias/<id>/eliminar/` | POST para eliminar categoría |
| `/gerente/menu/modificadores/` | Gestión de modificadores |
| `/gerente/menu/modificadores/crear/` | POST para crear modificador |
| `/gerente/menu/modificadores/<id>/eliminar/` | POST para eliminar modificador |
| `/gerente/menu/promociones/` | Gestión de promociones |
| `/gerente/menu/promociones/<id>/toggle/` | POST para activar/desactivar promoción |
| `/gerente/menu/promociones/<id>/eliminar/` | POST para eliminar promoción |
| `/gerente/mesas/` | Gestión de mesas |
| `/gerente/mesas/crud/` | CRUD de mesas (tabla/API) |
| `/gerente/mesas/<id>/eliminar/` | POST para eliminar mesa |
| `/gerente/mesas/<mesa_id>/asignar/` | POST para asignar mesero |
| `/gerente/empleados/` | Gestión de empleados |
| `/gerente/empleados/nuevo/` | Nuevo empleado |
| `/gerente/empleados/<id>/toggle/` | POST para activar/desactivar empleado |
| `/gerente/empleados/<id>/editar/` | Editar empleado |
| `/gerente/reportes/` | Reportes de ventas |
| `/gerente/auditoria/` | Registro de auditoría |
| `/gerente/stats/` | (JSON) Estadísticas para reportes |
| `/gerente/configuracion/` | Configuración general |
| `/gerente/menu/mesas/` | Alias de `/gerente/mesas/crud/` |
| `/gerente/menu/empleados/` | Alias de `/gerente/empleados/` |

---

## 🗃️ Modelo de datos

| Tabla | Descripción |
|---|---|
| `Empleado` | Personal del sistema con roles y credenciales (hereda de `AbstractBaseUser`) |
| `Mesa` | Mesas físicas, QR, PIN dinámico y estado |
| `SesionCliente` | Sesión de cada comensal (alias, token, estado) |
| `Producto` / `Categoria` | Catálogo del menú |
| `GrupoModificador` / `OpcionModificador` | Personalizaciones por producto |
| `Promocion` / `TipoPromocion` | Descuentos y ofertas activas |
| `Pedido` / `DetallePedido` / `DetalleModificador` | Registro completo de pedidos |
| `SolicitudPago` | Solicitudes de cuenta individuales o grupales |
| `Auditoria` | Registro de acciones críticas del sistema |

> El esquema completo con relaciones y restricciones está definido en los modelos de Django (`models.py` de cada app).

---

## 🚀 Tecnologías utilizadas

| Categoría | Tecnología |
|-----------|------------|
| **Backend** | Django 5.0 (Python 3.11) |
| **Base de datos** | MySQL 8 / MariaDB |
| **Frontend** | Django Templates, Bootstrap 5, Bootstrap Icons |
| **Estilos** | CSS personalizado (variables, diseño responsive) |
| **JavaScript** | Vanilla JS (fetch, polling, manipulación del DOM) |
| **Gráficas** | Chart.js 4 (solo en panel de reportes) |
| **Servidor** | Gunicorn + Nginx (producción) |

---

## 📁 Estructura del proyecto

```
mochi-matcha/
├── apps/                         # Todas las aplicaciones Django
│   ├── accounts/                 # Modelo Empleado, autenticación, decoradores
│   ├── auditoria/                # Registro de acciones críticas
│   ├── catalogs/                 # Catálogos simples (ModalidadIngreso, MetodoPago, etc.)
│   ├── cliente/                  # Vistas y templates del módulo cliente (móvil)
│   ├── cocina/                   # Vistas y templates del módulo cocina (KDS)
│   ├── gerente/                  # Vistas y templates del módulo gerente/admin
│   ├── menu/                     # Productos, Categorías, Modificadores, Promociones
│   ├── mesas/                    # Modelos Mesa y SesionCliente
│   ├── mesero/                   # Vistas y templates del módulo mesero
│   └── pedidos/                  # Pedido, DetallePedido, SolicitudPago
├── config/                       # Configuración de Django (settings, urls raíz, wsgi, asgi)
├── static/                       # CSS y JS globales (mochi.css, staff.css, cliente.css)
├── templates/                    # Plantillas base (base/*.html)
│   └── base/
│       ├── cliente_base.html
│       ├── login.html
│       └── staff_base.html
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── requirements.txt
└── README.md
```

---

<div align="center">

**Mochi Matcha** — Pensado para mejorar la experiencia del cliente y optimizar la operación del restaurante. 🍵

</div>
