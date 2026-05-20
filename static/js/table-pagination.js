/* =============================================================================
   Mochi Matcha — Paginación cliente para tablas largas
   -----------------------------------------------------------------------------
   Uso:
     <table data-paginate="20">  (page size opcional, default 20)
        ...
     </table>
   Renderiza controles "← Anterior  Página X de Y  Siguiente →" debajo de cada
   tabla marcada. Solo pagina filas reales (filas con un único TD de "Sin
   datos" se conservan sin paginar).

   Incluido automáticamente por staff_base.html en todas las vistas del panel.
   Compatible con ES5 para máxima compatibilidad en tablets/quioscos de cocina.
   ============================================================================= */
(function () {
  /**
   * Inicializa la paginación para una tabla específica.
   * Lee el atributo data-paginate como tamaño de página (default: 20).
   * Crea los controles de navegación y los inserta después de la tabla.
   * No hace nada si la tabla tiene ≤ pageSize filas.
   *
   * @param {HTMLTableElement} table - Elemento de tabla a paginar.
   */
  function paginate(table) {
    var pageSize = parseInt(table.getAttribute('data-paginate'), 10);
    if (!pageSize || pageSize < 1) pageSize = 20;

    var tbody = table.tBodies[0];
    if (!tbody) return;

    // Recolecta todas las filas del tbody como array nativo (ES5)
    var rows = Array.prototype.slice.call(tbody.rows);
    // No paginar la fila vacía ("Sin datos…")
    if (rows.length <= 1) return;
    if (rows.length <= pageSize) return;

    var totalPages = Math.ceil(rows.length / pageSize);
    var current = 0;  // Página activa (índice 0-based)

    // ── Construcción de los controles de paginación ──
    var controls = document.createElement('div');
    controls.className = 'mm-pagination';
    controls.style.cssText = 'display:flex;justify-content:center;align-items:center;gap:.75rem;padding:.75rem 1rem;border-top:1px solid var(--mm-border, #e5e0d8);background:var(--mm-cream, #faf7f2);font-size:.85rem;';

    // Botón "Anterior"
    var btnPrev = document.createElement('button');
    btnPrev.type = 'button';
    btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
    btnPrev.setAttribute('aria-label', 'Página anterior');
    btnPrev.style.cssText = 'background:var(--mm-white,#fff);border:1px solid var(--mm-border,#e5e0d8);border-radius:6px;width:32px;height:32px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--mm-green,#3D6B4F);';

    // Botón "Siguiente": clon del anterior para reutilizar estilos
    var btnNext = btnPrev.cloneNode(false);
    btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
    btnNext.setAttribute('aria-label', 'Página siguiente');

    // Indicador "Página X de Y · N filas"
    var info = document.createElement('span');
    info.style.cssText = 'font-weight:600;color:var(--mm-text,#1c1c1c);min-width:130px;text-align:center;';

    controls.appendChild(btnPrev);
    controls.appendChild(info);
    controls.appendChild(btnNext);

    // Insertar después de la tabla
    table.parentNode.insertBefore(controls, table.nextSibling);

    /**
     * Muestra solo las filas de la página actual y actualiza el texto del
     * indicador y el estado disabled/opacity de los botones.
     */
    function render() {
      var start = current * pageSize;
      var end = start + pageSize;
      for (var i = 0; i < rows.length; i++) {
        rows[i].style.display = (i >= start && i < end) ? '' : 'none';
      }
      info.textContent = 'Página ' + (current + 1) + ' de ' + totalPages
                       + '  ·  ' + rows.length + ' filas';
      btnPrev.disabled = current === 0;
      btnNext.disabled = current === totalPages - 1;
      // Feedback visual de botón deshabilitado (sin cambiar el cursor via CSS)
      btnPrev.style.opacity = btnPrev.disabled ? '.4' : '1';
      btnNext.style.opacity = btnNext.disabled ? '.4' : '1';
      btnPrev.style.cursor = btnPrev.disabled ? 'not-allowed' : 'pointer';
      btnNext.style.cursor = btnNext.disabled ? 'not-allowed' : 'pointer';
    }

    // Manejadores de los botones: verifican límites antes de cambiar de página
    btnPrev.addEventListener('click', function () {
      if (current > 0) { current--; render(); }
    });
    btnNext.addEventListener('click', function () {
      if (current < totalPages - 1) { current++; render(); }
    });

    // Render inicial de la primera página
    render();
  }

  /**
   * Busca todas las tablas con el atributo data-paginate en el documento
   * y aplica la paginación a cada una.
   */
  function init() {
    document.querySelectorAll('table[data-paginate]').forEach(paginate);
  }

  // Se ejecuta al cargar el DOM si el script se carga en el <head>,
  // o directamente si el documento ya está listo (carga al final del <body>).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
