from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('menu', '0008_alter_promocionproducto_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='promocion',
            name='imagen_url',
            field=models.CharField(
                blank=True,
                max_length=500,
                null=True,
                help_text='URL de imagen para banner de promoción (opcional).',
            ),
        ),
    ]
