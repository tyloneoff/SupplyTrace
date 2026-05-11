## Как запустить проект

Ниже инструкция для запуска проекта локально на Windows и Linux.

Проект запускается через Django development server:

```text
http://127.0.0.1:8000/
```

---

## Запуск на Windows

Инструкция рассчитана на запуск через `cmd` без ручной активации виртуального окружения.

### 1. Склонировать репозиторий

```cmd
git clone https://github.com/tyloneoff/SupplyTrace.git
cd SupplyTrace
```

### 2. Создать виртуальное окружение

```cmd
py -m venv .venv
```

### 3. Установить зависимости

```cmd
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Создать файл настроек `.env`

Для `cmd`:

```cmd
copy .env.example .env
```

Для PowerShell:

```powershell
Copy-Item .env.example .env
```

По умолчанию приложение само обновляет контракты из ЕИС при открытии карточки компании.
Настройки парсера можно изменить в `.env`:

```env
ZAKUPKI_SYNC_ENABLED=True
ZAKUPKI_CONTRACTS_LIMIT=100
ZAKUPKI_TIMEOUT=25
```

### 5. Применить миграции базы данных

```cmd
.\.venv\Scripts\python.exe manage.py migrate
```

### 6. Импортировать демонстрационные контракты, если нужен офлайн-режим

```cmd
.\.venv\Scripts\python.exe manage.py import_contracts_csv data\import\contracts_eis_demo_mirea_30.csv
```

Для ручной загрузки реальных контрактов из `zakupki.gov.ru` по ИНН:

```cmd
.\.venv\Scripts\python.exe manage.py sync_zakupki_contracts 7729040491
```

### 7. Запустить сервер

```cmd
.\.venv\Scripts\python.exe manage.py runserver
```

После запуска открыть в браузере:

```text
http://127.0.0.1:8000/
```

Для быстрой проверки можно открыть страницу компании из демонстрационного набора:

```text
http://127.0.0.1:8000/company/7729040491/
```

---

## Повторный запуск на Windows

Если проект уже был установлен ранее, достаточно выполнить:

```cmd
cd SupplyTrace
.\.venv\Scripts\python.exe manage.py runserver
```

---

## Запуск на Linux

Инструкция рассчитана на Ubuntu/Debian-подобные системы.

### 1. Склонировать репозиторий

```bash
git clone https://github.com/tyloneoff/SupplyTrace.git
cd SupplyTrace
```

### 2. Установить Python и venv, если они ещё не установлены

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

### 3. Создать виртуальное окружение

```bash
python3 -m venv .venv
```

### 4. Установить зависимости

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

### 5. Создать файл настроек `.env`

```bash
cp .env.example .env
```

По умолчанию приложение само обновляет контракты из ЕИС при открытии карточки компании.
Настройки парсера можно изменить в `.env`:

```env
ZAKUPKI_SYNC_ENABLED=True
ZAKUPKI_CONTRACTS_LIMIT=100
ZAKUPKI_TIMEOUT=25
```

### 6. Применить миграции базы данных

```bash
./.venv/bin/python manage.py migrate
```

### 7. Импортировать демонстрационные контракты, если нужен офлайн-режим

```bash
./.venv/bin/python manage.py import_contracts_csv data/import/contracts_eis_demo_mirea_30.csv
```

Для ручной загрузки реальных контрактов из `zakupki.gov.ru` по ИНН:

```bash
./.venv/bin/python manage.py sync_zakupki_contracts 7729040491
```

### 8. Запустить сервер

```bash
./.venv/bin/python manage.py runserver
```

После запуска открыть в браузере:

```text
http://127.0.0.1:8000/
```

Для быстрой проверки можно открыть страницу компании из демонстрационного набора:

```text
http://127.0.0.1:8000/company/7729040491/
```

---

## Повторный запуск на Linux

Если проект уже был установлен ранее, достаточно выполнить:

```bash
cd SupplyTrace
./.venv/bin/python manage.py runserver
```
