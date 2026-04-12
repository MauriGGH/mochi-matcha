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
      ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
      │ 📱 Cliente │ │ 🧑 Mesero  │ │ 🍳 Cocina  │ │ 💼 Gerente │
      │   (móvil)  │    (tablet)  │ │     KDS    │ │   (admin)  │
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

## 🗃️ Modelo de datos

| Tabla | Descripción |
|---|---|
| `Empleado` | Personal del sistema con roles y credenciales (hereda de AbstractBaseUser) |
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
      mochi-matcha/
      ├── config/ # Configuración de Django (settings, urls raíz)
      ├── accounts/ # Modelo Empleado, autenticación, decoradores
      ├── catalogs/ # Catálogos simples (ModalidadIngreso, MetodoPago, etc.)
      ├── menu/ # Productos, Categorías, Modificadores, Promociones
      ├── mesas/ # Modelos Mesa y SesionCliente
      ├── pedidos/ # Pedido, DetallePedido, SolicitudPago
      ├── auditoria/ # Registro de acciones críticas
      ├── cliente/ # Vistas y templates del módulo cliente (móvil)
      ├── mesero/ # Vistas y templates del módulo mesero
      ├── cocina/ # Vistas y templates del módulo cocina (KDS)
      ├── gerente/ # Vistas y templates del módulo gerente/admin
      ├── static/ # CSS, JS globales (mochi.css, staff.css, cliente.css)
      ├── templates/ # Plantillas base (base/cliente_base.html, staff_base.html, login.html)
      └── media/ # Imágenes subidas (productos, QR)


---

<div align="center">

**Mochi Matcha** — Pensado para mejorar la experiencia del cliente y optimizar la operación del restaurante. 🍵

</div>
