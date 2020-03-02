#!/usr/bin/env python3

import logging as log

from typing import List, Optional

import os
import lzma
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile
import subprocess

import arrow
import attr
import click


NOTES_DB_PATH = Path(
    "~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite").expanduser()

NOTES_BACKUP_DIR = Path("~/Documents/notesbackup/backups").expanduser()

INSTALL_DIR = Path("~/.notesbackup").expanduser()

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


@click.group()
@click.option("-v", "--verbose", is_flag=True, default=False, help="verbose operation")
def cli(verbose: bool) -> None:
  log.basicConfig()
  if verbose:
    log.root.setLevel(log.DEBUG)
  else:
    log.root.setLevel(log.INFO)


@cli.command()
@click.option("--src-db", default=NOTES_DB_PATH, help="path to the notes db to back up")
@click.option("--dest-dir", default=NOTES_BACKUP_DIR, help="destination where backups will be stored")
@click.option("--freq", default="hourly", type=click.Choice(FREQS), help="backup frequency")
def backup(src_db: str, dest_dir: str, freq: str) -> None:
  cfg = Config(src=Path(src_db), dst=Path(dest_dir), freq=freq)
  run(cfg)
  prune(cfg)
  log.info("backup complete")


def plist_kv(k: str, v: str, typ: str = "integer") -> List[str]:
  return [
    f"<key>{k}</key>",
    f"<{typ}>{v}</{typ}>",
  ]


@attr.s(auto_attribs=True, frozen=True, slots=True)
class Interval:
  minute: Optional[int]  = attr.ib(default=None)
  hour: Optional[int]    = attr.ib(default=None)
  day: Optional[int]     = attr.ib(default=None)
  weekday: Optional[int] = attr.ib(default=None)
  month: Optional[int]   = attr.ib(default=None)

  def to_plist(self) -> str:
    pairs = []
    if self.minute is not None:
      pairs.extend(plist_kv("Minute", str(self.minute)))
    if self.hour is not None:
      pairs.extend(plist_kv("Hour", str(self.hour)))
    if self.day is not None:
      pairs.extend(plist_kv("Day", str(self.day)))
    if self.weekday is not None:
      pairs.extend(plist_kv("Weekday", str(self.weekday)))
    if self.month is not None:
      pairs.extend(plist_kv("Month", str(self.month)))

    return "\n".join([f"\t\t{kv}" for kv in pairs])

INTERVAL_MAP = {
  "hourly": Interval(minute=47),
  "daily": Interval(hour=0, minute=24),
  "weekly": Interval(weekday=0, hour=11, minute=23),
  "monthly": Interval(day=1, hour=12, minute=18),
}

def launchd_template(freq: str) -> str:
  interval = INTERVAL_MAP[freq]
  return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>Disabled</key>
\t<false/>
\t<key>EnvironmentVariables</key>
\t<dict>
\t\t<key>PIPENV_DEFAULT_PYTHON_VERSION</key>
\t\t<string>/usr/bin/python3</string>
\t\t<key>PIPENV_NOSPIN</key>
\t\t<string>1</string>
\t\t<key>PIPENV_VENV_IN_PROJECT</key>
\t\t<string>1</string>
\t</dict>
\t<key>Label</key>
\t<string>com.slyphon.notes.backup.{freq}</string>
\t<key>KeepAlive</key>
\t<false/>
\t<key>ProgramArguments</key>
\t<array>
\t\t<string>/usr/local/bin/pipenv</string>
\t\t<string>run</string>
\t\t<string>./backup_notes.py</string>
\t\t<string>--freq={freq}</string>
\t\t<string>-v</string>
\t</array>
\t<key>RunAtLoad</key>
\t<true/>
\t<key>StartCalendarInterval</key>
\t<dict>
{interval.to_plist()}
\t</dict>
\t<key>WorkingDirectory</key>
\t<string>{INSTALL_DIR}</string>
</dict>
</plist>
"""

USER_AGENTS_DIR = Path("~/Library/LaunchAgents").expanduser()

def mk_plist_path(freq: str) -> Path:
  return USER_AGENTS_DIR.joinpath(f"com.slyphon.notes.backup.{freq}.plist")

@cli.command('install')
def install_launchd_plists() -> None:
  for f in FREQS:
    dest_path = mk_plist_path(f)
    with NamedTemporaryFile(mode="w", encoding="utf8", dir=dest_path.parent, delete=False) as tmp:
      try:
        tmp.write(launchd_template(f))
        tmp.flush()
        os.fsync(tmp.fileno())
        os.rename(tmp.name, str(dest_path))
      except Exception as e:
        try:
          os.unlink(tmp.name)
        except (OSError, IOError) as unlinke:
          log.error(f"failed to unlink tempfile", exc_info=unlinke)
          pass
        raise e from None
    log.info(f"created plist: {dest_path!s}")

@cli.command('load')
def load() -> None:
  for f in FREQS:
    plist = mk_plist_path(f)
    log.info(f"loading {plist}")
    subprocess.run(["/bin/launchctl", "load", "-w", plist], check=True)

@cli.command('unload')
def unload() -> None:
  for f in FREQS:
    plist = mk_plist_path(f)
    log.info(f"unloading {plist}")
    subprocess.run(["/bin/launchctl", "unload", "-w", plist], check=True)

if __name__ == '__main__':
  cli(auto_envvar_prefix='NOTES_BACKUP')
