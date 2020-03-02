#!/usr/bin/env python3

import os
from pathlib import Path
import sqlite3
import time
from tempfile import NamedTemporaryFile

NOTES_DB_PATH = Path(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite").expanduser()

NOTES_BACKUP_DIR = Path("~/Documents/notesbackup").expanduser()

NOW = time.localtime()
TS = time.strftime("%Y-%m-%dT%H:%M:%S%z", NOW)

BACKUP_FILE = NOTES_BACKUP_DIR.joinpath(f"notes-backup-{TS}.sql")

def progress(status, remaining, total):
  print(f'Copied {total-remaining} of {total} pages...')


def main():
  NOTES_BACKUP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
  with sqlite3.connect(":memory:") as mem:
    with sqlite3.connect(NOTES_DB_PATH, timeout=60.0) as back:
      back.backup(mem, pages=1, progress=progress)

    with NamedTemporaryFile(mode="w", encoding="utf8", dir=BACKUP_FILE.parent, delete=False) as tmp:
      try:
        for line in mem.iterdump():
          tmp.write(f"{line}\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        os.rename(tmp.name, BACKUP_FILE)
      except Exception as e:
        try:
          os.unlink(tmp.name)
        except Exception:
          pass
        raise e from None



if __name__ == '__main__':
  main()
