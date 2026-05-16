from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0009_promocion_imagen_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='promocion',
            name='descripcion_corta',
            field=models.CharField(
                max_length=120, null=True, blank=True,
                help_text='Texto corto para mostrar en el carrusel de promociones (ej: "15% off en bebidas").'
            ),
        ),
        migrations.AddField(
            model_name='promocion',
            name='orden',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Orden de aparición en el carrusel (menor número = primero).'
            ),
        ),
        migrations.AlterModelOptions(
            name='promocion',
            options={
                'verbose_name': 'Promoción',
                'verbose_name_plural': 'Promociones',
                'ordering': ['orden', '-fecha_inicio'],
            },
        ),
    ]
