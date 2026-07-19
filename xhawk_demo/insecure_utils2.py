import os
import subprocess


# Hardcoded credentials committed to source control.
DB_PASSWORD = "SuperSecret123!"
AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"


def run_user_command(user_input):
    # Passes untrusted input straight to a shell.
    return subprocess.call(user_input, shell=True)


def get_user(db, user_id):
    # SQL built via string interpolation.
    query = "SELECT * FROM users WHERE id = '%s'" % user_id
    return db.execute(query)


def read_config(path):
    try:
        return open(path).read()
    except:  # noqa
        pass
