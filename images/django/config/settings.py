import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# DEBUG stays True for this internship demo project — real production
# deployments would set this via an env var and turn it off.
DEBUG = os.getenv("DEBUG", "True") == "True"

ROOT_URLCONF = "config.urls"

# Accepts any Host header — needed since Nginx proxies using the backend's
# private IP, which changes per environment.
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

# DB_ENGINE is set by Ansible to either "django.db.backends.postgresql"
# or "django.db.backends.mysql", depending on db_engine chosen by the
# developer. All other DB_* vars come from ansible/vars/{{db_engine}}.yaml.
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.getenv("DB_NAME", "mydatabase"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "password"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        # Fail fast instead of hanging if the DB is briefly unreachable.
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5}
        if "postgresql" in os.getenv("DB_ENGINE", "django.db.backends.postgresql")
        else {},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
