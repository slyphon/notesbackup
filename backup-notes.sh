#!/bin/bash

set -euo pipefail
IFS=$'\n\t'

NOTES_BACKUP_INSTALL_PATH="${NOTES_BACKUP_INSTALL_PATH:-/opt/notesbackup}"
PIPENV="${PIPENV:-/usr/local/bin/pipenv}"

export PIPENV_DEFAULT_PYTHON_VERSION="/usr/bin/python3"
export PIPENV_VENV_IN_PROJECT=1
export PIPENV_NOSPIN=1
export PIPENV_PIPFILE="${NOTES_BACKUP_INSTALL_PATH}/Pipfile"

BACKUP_NOTES_PY="${NOTES_BACKUP_INSTALL_PATH}/backup_notes.py"

exec "${PIPENV}" run "${BACKUP_NOTES_PY}" "$@"
