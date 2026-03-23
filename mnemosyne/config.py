import os
from functools import lru_cache
from dotenv import load_dotenv


def _load():
    load_dotenv()


@lru_cache
def get_wp_base_url() -> str:
    _load()
    return os.environ["WP_BASE_URL"].rstrip("/")


@lru_cache
def get_wp_username() -> str:
    _load()
    return os.environ["WP_USERNAME"]


@lru_cache
def get_wp_app_password() -> str:
    _load()
    return os.environ["WP_APP_PASSWORD"]


@lru_cache
def get_openai_api_key() -> str:
    _load()
    return os.environ["OPENAI_API_KEY"]


def get_db_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "maria_luigia.db")


def get_sync_delay() -> float:
    _load()
    return float(os.environ.get("SYNC_DELAY", "1.0"))


def get_retry_max() -> int:
    _load()
    return int(os.environ.get("RETRY_MAX", "3"))


@lru_cache
def get_google_credentials_path() -> str:
    _load()
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
