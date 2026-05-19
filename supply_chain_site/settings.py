from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]

ZAKUPKI_SYNC_ENABLED = os.getenv('ZAKUPKI_SYNC_ENABLED', 'True').lower() == 'true'
ZAKUPKI_MOS_SYNC_ENABLED = os.getenv('ZAKUPKI_MOS_SYNC_ENABLED', 'True').lower() == 'true'
ZAKUPKI_CONTRACTS_LIMIT = int(os.getenv('ZAKUPKI_CONTRACTS_LIMIT', '100'))
ZAKUPKI_CONTRACT_LOOKBACK_DAYS = int(os.getenv('ZAKUPKI_CONTRACT_LOOKBACK_DAYS', '365'))
ZAKUPKI_TIMEOUT = int(os.getenv('ZAKUPKI_TIMEOUT', '25'))
ZAKUPKI_USER_AGENT = os.getenv('ZAKUPKI_USER_AGENT', 'SupplyTrace/1.0')
SUPPLYTRACE_LOCAL_DATA_TTL_HOURS = int(os.getenv('SUPPLYTRACE_LOCAL_DATA_TTL_HOURS', '24'))
TEKTORG_SYNC_ENABLED = os.getenv('TEKTORG_SYNC_ENABLED', 'True').lower() == 'true'
TEKTORG_TIMEOUT = int(os.getenv('TEKTORG_TIMEOUT', str(ZAKUPKI_TIMEOUT)))
TEKTORG_SECTION_CODES = os.getenv('TEKTORG_SECTION_CODES', '')

SBERBANK_AST_SYNC_ENABLED = os.getenv('SBERBANK_AST_SYNC_ENABLED', 'False').lower() == 'true'
SBERBANK_AST_TIMEOUT = int(os.getenv('SBERBANK_AST_TIMEOUT', str(ZAKUPKI_TIMEOUT)))
SBERBANK_AST_REGISTRY_URLS = os.getenv('SBERBANK_AST_REGISTRY_URLS', '')
BICOTENDER_SYNC_ENABLED = os.getenv('BICOTENDER_SYNC_ENABLED', 'False').lower() == 'true'
RTS_TENDER_SYNC_ENABLED = os.getenv('RTS_TENDER_SYNC_ENABLED', 'False').lower() == 'true'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'chain',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'supply_chain_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'supply_chain_site.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
