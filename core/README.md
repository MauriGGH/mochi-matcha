# App Core - Mochi Matcha

Esta app contiene los **modelos principales de la base de datos** de Mochi Matcha. Aquí se explica qué hace cada modelo y cómo se relaciona con los demás.

## Modelos principales

### Empleado
Tabla de los empleados del sistema.  
Campos importantes:  
- `nombre`, `usuario`, `contrasena_hash`  
- `rol`: puede ser mesero, cajero, cocina, gerente o admin  
- `activo`: indica si el empleado sigue activo

### ModalidadIngreso
Define cómo ingresa un cliente (QR, kiosco, asistido).

### Categoria
Categorías de productos (ej. bebidas, postres, etc.)

### TipoPromocion
Tipos de promociones disponibles (porcentaje, monto fijo, cantidad).

### Promocion
Promociones aplicables a productos.  
- Campos importantes: `titulo`, `valor`, `fecha_inicio`, `fecha_fin`, `codigo_cupon`  

### Mesa
Mesas del restaurante, con capacidad, ubicación y mesero asignado.

### Producto
Productos disponibles, con precio, categoría y disponibilidad.

### GrupoModificador y OpcionModificador
Permite crear opciones adicionales para productos (como toppings o extras).

### MetodoPago
Métodos de pago (Efectivo, Tarjeta, Mixto).

### EstadoSolicitud
Estados de las solicitudes de pago (pendiente, procesada, cancelada).

### SesionCliente
Registra la sesión de cada cliente en una mesa o modalidad de ingreso.

### PromocionProducto
Tabla intermedia para relacionar promociones con productos.

### Pedido
Registro de pedidos de clientes.  
Incluye referencias a `SesionCliente`, modalidad de ingreso y empleado que entrega.

### DetallePedido
Detalle de cada pedido: cantidad, producto y promoción aplicada.

### DetalleModificador
Opciones extra aplicadas a cada detalle de pedido.

### SolicitudPago
Registro de pagos realizados por clientes (individual o grupal).

### Auditoria
Registro de acciones realizadas en el sistema para control y seguimiento.

## Notas
- Todos los modelos están relacionados mediante **foreign keys** según la lógica del negocio.
- Para agregar o modificar datos se recomienda usar **Django Admin**.
- La app `core` funciona como **base unificada** antes de dividir en apps más pequeñas como `empleados` o `prestamos`.