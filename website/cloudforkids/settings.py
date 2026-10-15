"""
Django settings for cloudforkids project.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

import dj_database_url


def _load_env_file(path):
    """Tiny .env reader (KEY=value lines) so no extra package is needed."""
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

BASE_DIR = Path(__file__).resolve().parent.parent
_load_env_file(BASE_DIR / '.env')



def _env_bool(name, default=False):
    value = os.environ.get(name)
    return default if value is None or value == "" else value.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# DEBUG is OFF unless you turn it on (put DEBUG=True in your local .env only).
DEBUG = _env_bool("DEBUG", False)
TESTING = "test" in sys.argv

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured("Set the SECRET_KEY environment variable (see .env.example).")

ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if (DEBUG or TESTING) else "")
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")  # set automatically on Render
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
if not ALLOWED_HOSTS and not (DEBUG or TESTING):
    raise ImproperlyConfigured("Set ALLOWED_HOSTS (comma separated domain names), e.g. cloudforkids.co.ke,www.cloudforkids.co.ke")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")
if _render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
# A site behind HTTPS needs its own address in the trusted origins, or every login and form fails with "CSRF verification
# failed. Origin checking failed". Trust https://<host> for each real domain in ALLOWED_HOSTS unless set explicitly.
for _host in ALLOWED_HOSTS:
    _origin = f"https://{_host.lstrip('.')}"
    if _host not in ("*", "localhost", "127.0.0.1", "[::1]") and _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)

# HTTPS hardening (only when DEBUG is off)
if not DEBUG and not TESTING:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # the host's load balancer terminates TLS
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))  # raise to 31536000 once HTTPS is confirmed
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"
# Own cookie names: cookies are shared across ports on 127.0.0.1, so another local project (or an older copy of this one)
# can overwrite a plain "csrftoken"/"sessionid" and cause "CSRF token from POST incorrect".
CSRF_COOKIE_NAME = "c4k_csrftoken"
CSRF_FAILURE_VIEW = "core.views.csrf_failed"
SESSION_COOKIE_NAME = "c4k_sessionid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Cloud for Kids apps
    'accounts',
    'courses',
    'core',
    'dashboard',
    'billing',
    'live',
    'assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'core.middleware.UITranslationMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'cloudforkids.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.learner_chips',
                'dashboard.context_processors.resume_learning',
                'core.context_processors.site_settings',
                'core.context_processors.language',
                'core.context_processors.site_photos',
                'dashboard.context_processors.unread_messages',
                'assistant.context_processors.assistant',
            ],
        },
    },
]

WSGI_APPLICATION = 'cloudforkids.wsgi.application'


# PostgreSQL when DATABASE_URL is set (see .env.example), otherwise local SQLite.
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}
if 'pooler' in DATABASES['default'].get('HOST', ''):
    # Neon's pooled endpoint doesn't support server-side cursors
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English'), ('sw', 'Kiswahili')]
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365

TIME_ZONE = 'Africa/Nairobi'  # class times are entered and shown in Kenyan time

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_USE_FINDERS = DEBUG  # in production the files come from `collectstatic`
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Cloud for Kids custom settings
AUTH_USER_MODEL = 'accounts.User'
# Email: sent through Resend when RESEND_API_KEY is set (in .env); otherwise printed to the console for local testing.
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
EMAIL_BACKEND = (
    'core.resend_backend.ResendEmailBackend' if RESEND_API_KEY
    else 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_FROM', 'Cloud for Kids <onboarding@resend.dev>')
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')  # used for links in emails sent outside a web request
PASSWORD_RESET_TIMEOUT = 60 * 60 * 2  # reset links work for 2 hours

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'core:home'

# M-Pesa Express (STK Push) for plan payments. See billing/mpesa.py and .env.example.
MPESA_ENV = os.environ.get('MPESA_ENV', 'sandbox').strip().lower()
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', '').strip()
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', '').strip()
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '').strip()
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', '').strip()
MPESA_TILL_NUMBER = os.environ.get('MPESA_TILL_NUMBER', '').strip()  # only for a Buy Goods till
MPESA_CALLBACK_TOKEN = os.environ.get('MPESA_CALLBACK_TOKEN', '').strip()
MPESA_ACCOUNT_REFERENCE = os.environ.get('MPESA_ACCOUNT_REFERENCE', 'CloudForKids').strip()  # shown on the PIN prompt, max 12
# B2C payouts and balance checks (admin only). The credential is the initiator password encrypted with Safaricom's certificate.
MPESA_INITIATOR_NAME = os.environ.get('MPESA_INITIATOR_NAME', '').strip()
MPESA_SECURITY_CREDENTIAL = os.environ.get('MPESA_SECURITY_CREDENTIAL', '').strip()
SIBLING_DISCOUNT_PERCENT = int(os.environ.get('SIBLING_DISCOUNT_PERCENT', '10'))  # off a parent's 2nd, 3rd... child
BILLING_KRA_PIN = os.environ.get('BILLING_KRA_PIN', '').strip()  # printed on receipts when set

# Live online classes (https://livekit.io). LIVEKIT_URL is the project's wss:// address from the LiveKit Cloud dashboard.
LIVEKIT_URL = os.environ.get('LIVEKIT_URL', '').strip()
LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY', '').strip()
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET', '').strip()
LIVE_MAX_MINUTES = int(os.environ.get('LIVE_MAX_MINUTES', '180'))  # a class nobody ended counts as over after this long
LIVE_MAX_PARTICIPANTS = int(os.environ.get('LIVE_MAX_PARTICIPANTS', '60'))
LIVE_CLASSES_REQUIRE_PLAN = _env_bool('LIVE_CLASSES_REQUIRE_PLAN', False)  # on = learners need a plan with live classes
LIVE_BLOCKED_WORDS = _env_list('LIVE_BLOCKED_WORDS')  # extra words the class chat refuses, on top of live/moderation.py
# Recordings of the teacher go to S3-compatible storage (AWS S3, Cloudflare R2, Backblaze B2...). Empty = no recording.
LIVE_RECORDING_BUCKET = os.environ.get('LIVE_RECORDING_BUCKET', '').strip()
LIVE_RECORDING_ACCESS_KEY = os.environ.get('LIVE_RECORDING_ACCESS_KEY', '').strip()
LIVE_RECORDING_SECRET = os.environ.get('LIVE_RECORDING_SECRET', '').strip()
LIVE_RECORDING_REGION = os.environ.get('LIVE_RECORDING_REGION', 'auto').strip()
LIVE_RECORDING_ENDPOINT = os.environ.get('LIVE_RECORDING_ENDPOINT', '').strip()  # e.g. https://<account>.r2.cloudflarestorage.com

# AI assistant for admins and facilitators (Admin > Tools > AI assistant). Provider keys are added there, never in .env.
# Saved keys are encrypted with ASSISTANT_KEY_SECRET, or SECRET_KEY when it is empty: changing it means adding the keys again.
ASSISTANT_KEY_SECRET = os.environ.get('ASSISTANT_KEY_SECRET', '').strip()
ASSISTANT_INLINE = TESTING  # tests run the assistant's loop in the request instead of a background thread

SITE_NAME = 'Cloud for Kids'
SITE_TAGLINE = "Building Kenya's Cloud-Ready Generation"


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
}

if TESTING:
    # Fast, isolated tests: in-memory SQLite, in-memory email, cheap password hashing.
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    SECURE_SSL_REDIRECT = False
