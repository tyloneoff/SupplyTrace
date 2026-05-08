from django.db import models


class Company(models.Model):
    inn = models.CharField('ИНН', max_length=12, unique=True, db_index=True)
    name = models.CharField('Название', max_length=500)
    kpp = models.CharField('КПП', max_length=20, blank=True)
    ogrn = models.CharField('ОГРН', max_length=30, blank=True)

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
        on_delete=models.CASCADE,
        related_name='supplier_contracts',
    )
    purchase_url = models.URLField('Ссылка на закупку', blank=True)
    source_file = models.CharField('Файл-источник', max_length=500, blank=True)
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
