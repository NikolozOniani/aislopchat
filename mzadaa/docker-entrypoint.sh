#!/bin/sh
set -eu

# A Render disk hides /app/data from the built image. Make the newly mounted
# directory writable before starting the app as an unprivileged user.
DATA_DIR=$(dirname "${DATABASE_PATH:-/app/data/nightwave.db}")
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown chatter:chatter "$DATA_DIR"
    chmod 700 "$DATA_DIR"
    exec gosu chatter "$@"
fi
exec "$@"
