import os

SECRET_REFRESH_SECONDS = 10


def load_database_url():
    value = os.environ.get("DATABASE_URL")
    if value is None or value == "":
        raise RuntimeError("missing required environment variable: DATABASE_URL")
    return value
