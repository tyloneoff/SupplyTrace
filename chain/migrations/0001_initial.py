# Generated manually for starter project
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inn', models.CharField(db_index=True, max_length=12, unique=True, verbose_name='ИНН')),
                ('name', models.CharField(max_length=500, verbose_name='Название')),
                ('kpp', models.CharField(blank=True, max_length=20, verbose_name='КПП')),
                ('ogrn', models.CharField(blank=True, max_length=30, verbose_name='ОГРН')),
            ],
            options={
                'verbose_name': 'Компания',
                'verbose_name_plural': 'Компании',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='SearchHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inn', models.CharField(db_index=True, max_length=12, verbose_name='ИНН')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата поиска')),
            ],
            options={
                'verbose_name': 'История поиска',
                'verbose_name_plural': 'История поисков',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Contract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(db_index=True, max_length=150, verbose_name='Номер контракта')),
                ('title', models.CharField(blank=True, max_length=1000, verbose_name='Предмет контракта')),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name='Сумма')),
                ('date', models.DateField(blank=True, db_index=True, null=True, verbose_name='Дата заключения')),
                ('purchase_url', models.URLField(blank=True, verbose_name='Ссылка на закупку')),
                ('source_file', models.CharField(blank=True, max_length=500, verbose_name='Файл-источник')),
                ('imported_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата импорта')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_contracts', to='chain.company', verbose_name='Заказчик')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supplier_contracts', to='chain.company', verbose_name='Поставщик')),
            ],
            options={
                'verbose_name': 'Контракт',
                'verbose_name_plural': 'Контракты',
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='contract',
            constraint=models.UniqueConstraint(fields=('number', 'customer', 'supplier'), name='unique_contract_customer_supplier'),
        ),
    ]
