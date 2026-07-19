import subprocess


# Hardcoded credentials committed to source control.
DB_PASSWORD = "SuperSecret123!"
AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"


def run_user_command(user_input):
    # Untrusted input passed straight to a shell.
    return subprocess.call(user_input, shell=True)


def get_user(db, user_id):
    # SQL built via string interpolation.
    return db.execute("SELECT * FROM users WHERE id = '%s'" % user_id)


def read_config(path):
    try:
        return open(path).read()
    except:  # noqa
        pass
