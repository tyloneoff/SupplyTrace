# Supply Chain PoC

Django-проект для PoC-платформы анализа цепочек поставок.

Что умеет:

- поиск по ИНН;
- карточка компании;
- история поисков;
- таблица контрактов;
- граф контрагентов;
- HTML-отчёт;
- получение карточки компании через DaData по ИНН;
- импорт демонстрационного набора контрактов из CSV.

## Запуск на Windows без активации venv

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Открыть:

```text
http://127.0.0.1:8000/
```

## DaData

Чтобы сайт сам подтягивал карточку компании по ИНН, добавь токен в `.env`:

```env
DADATA_TOKEN=твой_токен
```

После изменения `.env` перезапусти сервер.

Без токена сайт всё равно работает, но будет искать компании только в локальной базе.

## Импорт демонстрационных контрактов

В проекте есть пример файла:

```text
data/import/contracts_demo.csv
```

Загрузить его можно так:

```powershell
.\.venv\Scripts\python.exe manage.py import_contracts_csv data\import\contracts_demo.csv
```

После этого можно открыть:

```text
http://127.0.0.1:8000/company/7736207543/
```

## Формат CSV

Обязательные колонки:

```text
number,date,price,customer_inn,customer_name,supplier_inn,supplier_name
```

Дополнительные колонки:

```text
title,customer_kpp,customer_ogrn,supplier_kpp,supplier_ogrn,purchase_url
```

Дата поддерживается в форматах:

```text
2026-02-10
10.02.2026
```

## Логика текущего PoC

Текущий вариант честно разделяет источники:

```text
DaData -> карточка компании по ИНН
CSV/локальная база -> демонстрационные контракты для графа и таблиц
Django -> интерфейс, история поисков, граф, отчёт
```

Это нормальный вариант для PoC, потому что проект показывает работу всей цепочки без сложной официальной интеграции с ЕИС.
