import os
import shlex
import subprocess


# Credentials are injected via environment variables.
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")


def run_user_command(user_input):
    args = shlex.split(user_input)
    if not args or args[0] != "status":
        raise ValueError("unsupported command")
    return subprocess.call(args, shell=False)


def get_user(db, user_id):
    query = "SELECT * FROM users WHERE id = ?"
    return db.execute(query, (user_id,))


def read_config(path):
    try:
        return open(path).read()
    except:  # noqa
        pass
