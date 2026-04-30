from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pedido",
            name="motivo_cancelacion",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
