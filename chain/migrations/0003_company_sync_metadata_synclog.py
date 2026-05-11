from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chain', '0002_contract_closed_supplier'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='last_synced_at',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                null=True,
                verbose_name='Последнее обновление',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='last_sync_status',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ok', 'Обновлено'),
                    ('warning', 'С предупреждением'),
                    ('error', 'Ошибка'),
                    ('disabled', 'Отключено'),
                ],
                max_length=20,
                verbose_name='Статус последнего обновления',
            ),
        ),
        migrations.AddField(
            model_name='company',
            name='last_sync_message',
            field=models.CharField(
                blank=True,
                max_length=300,
                verbose_name='Итог последнего обновления',
            ),
        ),
        migrations.CreateModel(
            name='SyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inn', models.CharField(db_index=True, max_length=12, verbose_name='ИНН')),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('ok', 'Обновлено'),
                            ('warning', 'С предупреждением'),
                            ('error', 'Ошибка'),
                            ('disabled', 'Отключено'),
                        ],
                        max_length=20,
                        verbose_name='Статус',
                    ),
                ),
                ('message', models.CharField(blank=True, max_length=300, verbose_name='Итог')),
                ('fetched', models.PositiveIntegerField(default=0, verbose_name='Получено')),
                ('imported', models.PositiveIntegerField(default=0, verbose_name='Загружено')),
                ('updated', models.PositiveIntegerField(default=0, verbose_name='Обновлено')),
                ('unchanged', models.PositiveIntegerField(default=0, verbose_name='Без изменений')),
                ('skipped', models.PositiveIntegerField(default=0, verbose_name='Пропущено')),
                ('source_snapshot', models.JSONField(blank=True, default=list, verbose_name='Статус источников')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата проверки')),
                (
                    'company',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='sync_logs',
                        to='chain.company',
                        verbose_name='Компания',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Журнал обновления',
                'verbose_name_plural': 'Журнал обновлений',
                'ordering': ['-created_at'],
            },
        ),
    ]
