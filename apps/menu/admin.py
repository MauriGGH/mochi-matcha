from django.contrib import admin
from .models import Categoria, Producto, GrupoModificador, OpcionModificador, Promocion, TipoPromocion

admin.site.register(Categoria)
admin.site.register(Producto)
admin.site.register(GrupoModificador)
admin.site.register(OpcionModificador)
admin.site.register(Promocion)
admin.site.register(TipoPromocion)