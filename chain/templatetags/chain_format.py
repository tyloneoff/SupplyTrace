from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def money(value):
    if value in (None, ''):
        return 'сумма не указана'

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return 'сумма не указана'

    if amount == 0:
        return 'сумма не указана'

    return f'{amount:,.2f} ₽'.replace(',', ' ').replace('.', ',')
