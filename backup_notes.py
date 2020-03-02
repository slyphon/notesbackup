#!/usr/bin/env python3

import logging as log

import os
import lzma
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile

import arrow
import attr
import click


NOTES_DB_PATH = Path(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite").expanduser()

NOTES_BACKUP_DIR = Path("~/Documents/notesbackup/backups").expanduser()

@attr.s(auto_attribs=True, frozen=True, slots=True)
class Config:
  src: Path
  dst: Path
  freq: str

FREQS = [
  "hourly",
  "daily",
  "weekly",
  "monthly",
]

NUM_FREQS = {
  "hourly": 24,
  "daily": 7,
  "weekly": 8,
  "monthly": 24,
}

NOW = arrow.now()
TS = NOW.format("YYYYMMDDHHmmssZZ")

def backup_path(cfg: Config) -> Path:
  return cfg.dst.joinpath(f"{TS}_{cfg.freq}.sql.xz")


def prune(cfg: Config) -> None:
  backups = sorted(list(cfg.dst.glob(f"*_{cfg.freq}.sql.xz")))
  too_many = len(backups) - NUM_FREQS[cfg.freq]
  if too_many > 0:
    for b in backups[0:too_many]:
      log.info(f"pruning: {b!s}")
      b.unlink()

def run(cfg: Config) -> None:
  cfg.dst.mkdir(mode=0o700, parents=True, exist_ok=True)

  dest_path = backup_path(cfg)

  def progress(status, remaining, total):
    log.debug(f'Copied {total-remaining} of {total} pages')

  with sqlite3.connect(":memory:") as mem:
    with sqlite3.connect(str(cfg.src), timeout=60.0) as back:
      back.backup(mem, pages=16, progress=progress)

    with NamedTemporaryFile(mode="w+b", dir=dest_path.parent, delete=False) as tmp:
      try:
        with lzma.LZMAFile(tmp, mode="w", format=lzma.FORMAT_XZ, check=lzma.CHECK_SHA256) as out:
          # noinspection PyTypeChecker
          for line in mem.iterdump():
            out.write(f"{line}\n".encode("utf8"))
          out.flush()
        os.fsync(tmp.fileno())
        os.rename(tmp.name, str(dest_path))
        log.info(f"created backup {dest_path!s}")
      except Exception as e:
        try:
          os.unlink(tmp.name)
        except (OSError, IOError) as unlinke:
          log.error(f"failed to unlink tempfile", exc_info=unlinke)
          pass
        raise e from None


@click.command()
@click.option("--src-db", default=NOTES_DB_PATH, help="path to the notes db to back up")
@click.option("--dest-dir", default=NOTES_BACKUP_DIR, help="destination where backups will be stored")
@click.option("--freq", default="hourly", type=click.Choice(FREQS), help="backup frequency")
@click.option("-v", "--verbose", is_flag=True, default=False, help="verbose operation")
def backup(src_db: str, dest_dir: str, freq: str, verbose: bool) -> None:
  log.basicConfig()
  if verbose:
    log.root.setLevel(log.DEBUG)
  else:
    log.root.setLevel(log.INFO)
  cfg = Config(src=Path(src_db), dst=Path(dest_dir), freq=freq)
  run(cfg)
  prune(cfg)
  log.info("backup complete")


if __name__ == '__main__':
  backup(auto_envvar_prefix='NOTES_BACKUP')
