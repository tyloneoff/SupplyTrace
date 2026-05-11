from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chain', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contract',
            name='supplier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='supplier_contracts',
                to='chain.company',
                verbose_name='Поставщик',
            ),
        ),
        migrations.AddField(
            model_name='contract',
            name='is_closed',
            field=models.BooleanField(default=False, verbose_name='Закрытая закупка'),
        ),
        migrations.AddField(
            model_name='contract',
            name='supplier_disclosed',
            field=models.BooleanField(default=True, verbose_name='Поставщик раскрыт'),
        ),
    ]
