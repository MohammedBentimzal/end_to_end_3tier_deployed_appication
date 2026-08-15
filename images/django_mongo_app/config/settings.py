import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
DEBUG = os.getenv("DEBUG", "True") == "True"

ROOT_URLCONF = "config.urls"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "backend",
]

MIDDLEWARE = []

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    }
]

STATIC_URL = "/static/"
STATICFILES_DIRS = ["static"]

# Django's own ORM has no built-in MongoDB backend (community adapters like
# djongo are unreliable across Django versions), so this image talks to
# Mongo directly via pymongo in backend/views.py instead of going through
# Django's DATABASES/ORM layer. The "dummy" backend just lets Django boot
# without requiring a SQL driver it will never actually use.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy",
    }
}

# Mongo connection details, read directly by backend/views.py via pymongo —
# same env var names as every other backend/database combination in this
# project, injected by Ansible from ansible/vars/mongo.yaml.
MONGO_HOST = os.getenv("DB_HOST", "localhost")
MONGO_PORT = os.getenv("DB_PORT", "27017")
MONGO_DB_NAME = os.getenv("DB_NAME", "mydatabase")
MONGO_USER = os.getenv("DB_USER", "admin")
MONGO_PASSWORD = os.getenv("DB_PASSWORD", "password")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
