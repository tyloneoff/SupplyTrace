from django.db import models


class Company(models.Model):
    SYNC_STATUS_OK = 'ok'
    SYNC_STATUS_WARNING = 'warning'
    SYNC_STATUS_ERROR = 'error'
    SYNC_STATUS_DISABLED = 'disabled'

    SYNC_STATUS_CHOICES = [
        (SYNC_STATUS_OK, 'Обновлено'),
        (SYNC_STATUS_WARNING, 'С предупреждением'),
        (SYNC_STATUS_ERROR, 'Ошибка'),
        (SYNC_STATUS_DISABLED, 'Отключено'),
    ]

    inn = models.CharField('ИНН', max_length=12, unique=True, db_index=True)
    name = models.CharField('Название', max_length=500)
    kpp = models.CharField('КПП', max_length=20, blank=True)
    ogrn = models.CharField('ОГРН', max_length=30, blank=True)
    last_synced_at = models.DateTimeField('Последнее обновление', null=True, blank=True, db_index=True)
    last_sync_status = models.CharField(
        'Статус последнего обновления',
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        blank=True,
    )
    last_sync_message = models.CharField('Итог последнего обновления', max_length=300, blank=True)

    class Meta:
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.inn})'


class Contract(models.Model):
    number = models.CharField('Номер контракта', max_length=150, db_index=True)
    title = models.CharField('Предмет контракта', max_length=1000, blank=True)
    price = models.DecimalField('Сумма', max_digits=18, decimal_places=2, default=0)
    date = models.DateField('Дата заключения', null=True, blank=True, db_index=True)
    customer = models.ForeignKey(
        Company,
        verbose_name='Заказчик',
        on_delete=models.CASCADE,
        related_name='customer_contracts',
    )
    supplier = models.ForeignKey(
        Company,
        verbose_name='Поставщик',
        on_delete=models.SET_NULL,
        related_name='supplier_contracts',
        null=True,
        blank=True,
    )
    purchase_url = models.URLField('Ссылка на закупку', blank=True)
    source_file = models.CharField('Файл-источник', max_length=500, blank=True)
    is_closed = models.BooleanField('Закрытая закупка', default=False)
    supplier_disclosed = models.BooleanField('Поставщик раскрыт', default=True)
    imported_at = models.DateTimeField('Дата импорта', auto_now_add=True)

    class Meta:
        verbose_name = 'Контракт'
        verbose_name_plural = 'Контракты'
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['number', 'customer', 'supplier'],
                name='unique_contract_customer_supplier',
            )
        ]

    def __str__(self):
        return self.number


class SearchHistory(models.Model):
    inn = models.CharField('ИНН', max_length=12, db_index=True)
    created_at = models.DateTimeField('Дата поиска', auto_now_add=True)

    class Meta:
        verbose_name = 'История поиска'
        verbose_name_plural = 'История поисков'
        ordering = ['-created_at']

    def __str__(self):
        return self.inn


class SyncLog(models.Model):
    STATUS_CHOICES = Company.SYNC_STATUS_CHOICES

    inn = models.CharField('ИНН', max_length=12, db_index=True)
    company = models.ForeignKey(
        Company,
        verbose_name='Компания',
        on_delete=models.SET_NULL,
        related_name='sync_logs',
        null=True,
        blank=True,
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES)
    message = models.CharField('Итог', max_length=300, blank=True)
    fetched = models.PositiveIntegerField('Получено', default=0)
    imported = models.PositiveIntegerField('Загружено', default=0)
    updated = models.PositiveIntegerField('Обновлено', default=0)
    unchanged = models.PositiveIntegerField('Без изменений', default=0)
    skipped = models.PositiveIntegerField('Пропущено', default=0)
    source_snapshot = models.JSONField('Статус источников', default=list, blank=True)
    created_at = models.DateTimeField('Дата проверки', auto_now_add=True)

    class Meta:
        verbose_name = 'Журнал обновления'
        verbose_name_plural = 'Журнал обновлений'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.inn}: {self.get_status_display()}'
