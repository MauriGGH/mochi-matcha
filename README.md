<div align="center">

# 🍵 Mochi Matcha

### Sistema de Gestión de Pedidos para Cafetería

*Desde el escaneo del QR hasta el cierre de mesa — todo en un solo sistema.*

<br/>

[![Django](https://img.shields.io/badge/Django_5-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap_5-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![MariaDB](https://img.shields.io/badge/MariaDB_10.6-4479A1?style=for-the-badge&logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

> **🚀 Versión de producción** — Esta es la rama desplegada en el servidor.  
> Para instrucciones de despliegue, actualización y mantenimiento consulta [`DEPLOYMENT.md`](DEPLOYMENT.md).

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
| 💳 **Cobro flexible** | Pago individual o grupal — efectivo, tarjeta, mixto o PayPal |
| 📊 **Reportes de gestión** | Ventas, afluencia, tiempos de servicio y auditoría de cancelaciones |
| ⚙️ **Configuración desde la UI** | Credenciales PayPal, modo mantenimiento y umbrales KDS sin tocar el servidor |

---

## 🏗️ Arquitectura

```
      ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
      │ 📱 Cliente │ │ 🧑 Mesero  │ │ 🍳 Cocina  │ │ 💼 Gerente │
      │   (móvil)  │ │  (tablet)  │ │     KDS    │ │   (admin)  │
      └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
            │              │              │              │
            └──────────────┴──────────────┴──────────────┘
                                    │  HTTPS
                   ┌────────────────▼────────────────┐
                   │    Cloudflare Edge (CDN + TLS)   │
                   └────────────────┬────────────────┘
                                    │ túnel cifrado
                   ┌────────────────▼────────────────┐
                   │  cloudflared (network_mode: host)│
                   │  → localhost:80                  │
                   └────────────────┬────────────────┘
                                    │ HTTP
                   ┌────────────────▼────────────────┐
                   │     Nginx Proxy Manager          │
                   │  (Docker) → 172.x.x.1:8002       │
                   └────────────────┬────────────────┘
                                    │
                   ┌────────────────▼────────────────┐
                   │  Django 5 + Gunicorn — :8002     │
                   │  (Docker, build desde Dockerfile)│
                   └────────────────┬────────────────┘
                                    │
                   ┌────────────────▼────────────────┐
                   │       MariaDB 10.6 (Docker)      │
                   └─────────────────────────────────┘
```

**Frontend:** Django Templates + Bootstrap 5 + Chart.js — diseño responsive, polling con JavaScript vanilla  
**Backend:** Django 5 (Python 3.11) — autenticación dual (clientes vía cookie, staff vía sesión Django)  
**Base de datos:** MariaDB 10.6  
**Infraestructura:** Docker Compose en Raspberry Pi, expuesto via Cloudflare Tunnel + Nginx Proxy Manager

---

## 📱 Módulos del sistema

<details>
<summary><strong>🧑‍💻 Aplicación Cliente (móvil)</strong></summary>

<br/>

- **Acceso**: QR → alias → PIN generado o recuperación de sesión existente
- **Menú**: Categorías, productos con modificadores y notas especiales
- **Carrito**: Resumen, ajuste de cantidades y envío a cocina
- **Seguimiento**: Estado de pedidos activos en tiempo real
- **Pago**: PayPal en línea o solicitud de cuenta al mesero
- **Acciones**: Solicitud de ayuda al mesero

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
- **Reportes**: Ventas por período, top productos, afluencia por mesa, tiempos de servicio, promociones y auditoría — exportación a PDF
- **Configuración**: Credenciales PayPal (live/sandbox), modo mantenimiento, umbrales del semáforo KDS

</details>

---

## ⚙️ Configuración de PayPal

Las credenciales se gestionan **desde el panel del gerente** en `Configuración`. Los valores guardados ahí tienen **prioridad sobre el `.env`** — no es necesario editar el servidor para cambiar entre sandbox y live.

| Clave | Descripción |
|---|---|
| `paypal_client_id` | Client ID de la app PayPal |
| `paypal_secret` | Secret de la app PayPal |
| `paypal_modo` | `sandbox` o `live` |

El `.env` actúa como fallback para instalaciones nuevas donde la BD aún no tiene configuración.

---

## 🧪 Rutas principales

### 🔓 Públicas

| URL | Descripción |
|-----|-------------|
| `/` | Redirige a `/bienvenida/` |
| `/bienvenida/` | Pantalla inicial — ingresar PIN o crear sesión |
| `/bienvenida/crear/<mesa_id>/` | Crear nueva sesión en una mesa |
| `/bienvenida/recuperar/<mesa_id>/` | Recuperar sesión existente con PIN |

### 🧑‍💻 Cliente

| URL | Descripción |
|-----|-------------|
| `/menu/` | Menú digital |
| `/carrito/` | Ver y gestionar carrito |
| `/carrito/confirmar/` | Enviar pedido a cocina |
| `/pedidos/` | Estado de pedidos activos |
| `/pago/paypal/crear/` | Iniciar pago PayPal |

### 🧑‍🍳 Mesero

| URL | Descripción |
|-----|-------------|
| `/mesero/login/` | Login |
| `/mesero/mapa/` | Mapa de mesas |
| `/mesero/alertas/` | Alertas y solicitudes de cuenta |
| `/mesero/pago/` | Procesar pago |
| `/mesero/asistido/` | Pedido asistido |

### 🍳 Cocina

| URL | Descripción |
|-----|-------------|
| `/cocina/login/` | Login |
| `/cocina/kds/` | Pantalla KDS |

### 💼 Gerente

| URL | Descripción |
|-----|-------------|
| `/gerente/login/` | Login |
| `/gerente/dashboard/` | Panel principal |
| `/gerente/floor-plan/` | Plano de mesas (tiempo real) |
| `/gerente/menu/` | Gestión de productos |
| `/gerente/mesas/` | Gestión de mesas |
| `/gerente/empleados/` | Gestión de empleados |
| `/gerente/reportes/` | Reportes (ventas, productos, equipo, operativo) |
| `/gerente/auditoria/` | Registro de auditoría |
| `/gerente/configuracion/` | Configuración general y PayPal |

---

## 🗃️ Modelo de datos

| Tabla | Descripción |
|---|---|
| `Empleado` | Personal con roles y credenciales (hereda de `AbstractBaseUser`) |
| `Mesa` | Mesas físicas, QR, PIN dinámico y estado |
| `SesionCliente` | Sesión de cada comensal (alias, token, estado) |
| `Producto` / `Categoria` | Catálogo del menú |
| `GrupoModificador` / `OpcionModificador` | Personalizaciones por producto |
| `Promocion` / `TipoPromocion` | Descuentos y ofertas activas |
| `Pedido` / `DetallePedido` / `DetalleModificador` | Registro completo de pedidos |
| `SolicitudPago` | Solicitudes de cuenta individuales o grupales |
| `Configuracion` | Pares clave-valor de config global (PayPal, KDS, mantenimiento) |
| `Auditoria` | Registro de acciones críticas |

---

## 📁 Estructura del proyecto

```
mochi-matcha-production/
├── apps/
│   ├── accounts/     # Usuario custom, autenticación, decoradores de rol
│   ├── auditoria/    # Registro de acciones sensibles
│   ├── catalogs/     # Catálogos simples (MetodoPago, ModalidadIngreso…)
│   ├── cliente/      # App del cliente final (cookie de sesión, sin login Django)
│   ├── cocina/       # KDS
│   ├── gerente/      # Panel de administración, reportes y configuración
│   ├── menu/         # Productos, Categorías, Modificadores, Promociones
│   ├── mesas/        # Mesa, SesionCliente, AlertaMesero, QR
│   ├── mesero/       # Panel del mesero, cobro, PayPal
│   └── pedidos/      # Pedido, DetallePedido, SolicitudPago
├── config/           # settings.py, urls.py, wsgi.py, middleware.py
├── static/           # CSS y JS globales
├── templates/        # Plantillas base
├── media/            # Imágenes subidas (bind mount → ./media en el host)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md         # Este archivo
└── DEPLOYMENT.md     # Guía de despliegue, actualización y mantenimiento
```

---

<div align="center">

**Mochi Matcha** — Pensado para mejorar la experiencia del cliente y optimizar la operación del restaurante. 🍵  
¿Vas a desplegar o actualizar el sistema? Consulta [`DEPLOYMENT.md`](DEPLOYMENT.md).

</div>
