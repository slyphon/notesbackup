import plistlib as P
import subprocess
from glob import glob
from os.path import join, basename, splitext


def convert_to_xml(path):
  with open(path, 'rb') as fp:
    result = subprocess.run(
      ["/usr/bin/plutil", "-convert", "xml1", "-", "-o", "-"],
      capture_output=True,
      stdin=fp,
      check=True)
    return result.stdout


def find_data_idx(rec):
  for i, x in enumerate(rec):
    if x == 'AppleSDGothicNeo':
      return i + 1
  return None

def extract_data(d):
    objs = d['$objects']
    i = find_data_idx(objs)
    if i is not None:
      while i < len(objs):
        if not isinstance(objs[i], str):
          i += 1
          continue

        elif len(objs[i]) >= len(objs[i+1]):
          return objs[i]
        else:
          return objs[i+1]
    else:
      return None

OUTPUT_DIR = "converted"


def main():
  failed = []
  res = []
  for path in glob('backup/*.anote'):
    try:
      d = P.loads(convert_to_xml(path))
      data = extract_data(d)
      if data is None:
        failed.append(path)
      else:
        output_path = join(OUTPUT_DIR, splitext(basename(path))[0] + ".txt")
        with open(output_path, 'w', encoding='utf8') as fp:
          print(splitext(basename(path))[0], file=fp)
          print("", file=fp)
          print(data, file=fp)
          fp.write("\n")
          fp.flush()

        print(f"wrote {output_path}")
    except TypeError:
      print(f"type error in file {path}")
      return
  print("failed inputs: ")
  print("\n".join(failed))



if __name__ == '__main__':
  main()
