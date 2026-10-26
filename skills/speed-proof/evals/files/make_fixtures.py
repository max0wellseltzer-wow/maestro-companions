"""Write one of the speed-proof eval fixtures: a tiny, deliberately slow project as a git repo with one commit `fixture`.

    python make_fixtures.py e1 TARGET_DIR [--rows 100000 --symbols 100]
    python make_fixtures.py e2 TARGET_DIR [--files 1500 --words 400]
    python make_fixtures.py e3 TARGET_DIR [--rows 2000 --side 1500]
    python make_fixtures.py all PARENT_DIR

Data is generated deterministically from a seed (nothing large is stored). Each fixture holds the traps the eval needs:
E1 a timestamp header (a byte diff fails unless it is stripped) and 10-decimal sums (summation order shows);
E2 a header re-parse plus a hand-rolled stemmer per query (a real speed-up needs a derived copy that must stay honest);
E3 a heavy import hidden one level down (lookup -> common -> heavy) plus a quadratic dedupe, and a --full mode that needs heavy.
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

E1_GEN = '''"""Generate data.csv: a deterministic random walk per symbol, rows written in shuffled order."""
import csv, random, sys
from datetime import date, timedelta

def main(path, rows=100000, symbols=100, seed=1):
    rng = random.Random(seed)
    per = rows // symbols
    out = []
    for k in range(symbols):
        sym = f"S{k:03d}"
        price, day = rng.uniform(5, 200), date(2022, 1, 3)
        for _ in range(per):
            price = max(1.0, price * (1 + rng.gauss(0, 0.02)))
            out.append((sym, day.isoformat(), f"{price:.4f}", str(int(rng.uniform(1e4, 5e6)))))
            day += timedelta(days=1)
    rng.shuffle(out)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "date", "close", "volume"])
        w.writerows(out)

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "data.csv", int(a[1]) if len(a) > 1 else 100000, int(a[2]) if len(a) > 2 else 100, int(a[3]) if len(a) > 3 else 1)
'''

E1_REPORT = '''"""report.py DATA.csv: per-symbol last close and 20-day average dollar volume, ranked."""
import csv, sys
from datetime import UTC, datetime


def main(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    symbols = sorted({r["symbol"] for r in rows})
    print(f"generated: {datetime.now(UTC).isoformat(timespec='seconds')}  source: {path} ({len(rows)} rows)")
    print(f"{'rank':>4} {'symbol':<8} {'last_close':>12} {'avg20_dollar_volume':>24}")
    table = []
    for s in symbols:
        mine = [r for r in rows if r["symbol"] == s]
        mine.sort(key=lambda r: r["date"])
        last20 = mine[-20:]
        avg = sum(float(r["close"]) * float(r["volume"]) for r in last20) / len(last20)
        table.append((avg, s, float(mine[-1]["close"])))
    table.sort(key=lambda t: (-t[0], t[1]))
    for i, (avg, s, close) in enumerate(table, 1):
        print(f"{i:>4} {s:<8} {close:>12.4f} {avg:>24.10f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data.csv")
'''

E1_README = '''# report
`python gen.py data.csv` writes the data (deterministic). `python report.py data.csv` prints the ranked table.
The first line of the output carries the time it was generated.
'''

E2_GEN = '''"""Generate notes/*.md: a header (title, tags, date) then a body of words; deterministic."""
import random, sys
from pathlib import Path

WORDS = ("market open close volume price trend signal noise order book spread quote bid ask fill route venue session "
         "earnings guidance margin revenue growth decline rally slump breakout breakdown support resistance average "
         "median spike drought liquid thin crowded quiet calm storm trading screening filtering ranking testing proving "
         "doubting measuring reading writing editing noting walking running jumping thinking hoping waiting").split()

def main(folder, files=1500, words=400, seed=1):
    rng = random.Random(seed)
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(files):
        body = " ".join(rng.choice(WORDS) for _ in range(words))
        if i % 97 == 0:
            body += " golden volume spike"
        tags = ",".join(rng.sample(WORDS, 3))
        text = f"title: Note {i:04d}\\ntags: {tags}\\ndate: 2026-{1 + i % 12:02d}-{1 + i % 28:02d}\\n\\n{body}\\n"
        (out / f"note_{i:04d}.md").write_text(text, encoding="utf-8")

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "notes", int(a[1]) if len(a) > 1 else 1500, int(a[2]) if len(a) > 2 else 400, int(a[3]) if len(a) > 3 else 1)
'''

E2_FIND = '''"""find.py PHRASE [FOLDER]: the notes whose body contains PHRASE (stemmed words, in order), oldest first."""
import os, re, sys

HEADER = re.compile(r"^(title|tags|date):\\s*(.*)$")
SUFFIXES = ("ingly", "edly", "ing", "ed", "ly", "es", "s")


def stem(word):
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) > len(suf) + 2:
            return word[: -len(suf)]
    return word


def load(folder):
    docs = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            text = f.read()
        head, _, body = text.partition("\\n\\n")
        meta = {}
        for line in head.splitlines():
            m = HEADER.match(line)
            if m:
                meta[m.group(1)] = m.group(2)
        words = [stem(w) for w in re.findall(r"[a-z]+", body.lower())]
        docs.append((name, meta, words))
    return docs


def main(phrase, folder="notes"):
    want = [stem(w) for w in re.findall(r"[a-z]+", phrase.lower())]
    hits = []
    for name, meta, words in load(folder):
        n = len(want)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == want:
                hits.append((meta.get("date", ""), name, meta.get("title", "")))
                break
    hits.sort()
    for d, name, title in hits:
        print(f"{d}  {name}  {title}")
    print(f"{len(hits)} notes match {phrase!r}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "notes")
'''

E2_README = '''# notes search
`python gen.py notes` writes the notes. `python find.py "golden volume spike"` lists the notes that contain the phrase,
oldest first, then a count line. People edit, add and delete notes all day long.
'''

E3_HEAVY = '''"""heavy.py: a pair table used by build.py and by lookup.py --full. Building it is slow."""
SIDE = __SIDE__
TABLE = [[((i * j) % 97) + ((i ^ j) & 7) for j in range(SIDE)] for i in range(SIDE)]


def summary(name):
    acc = 0
    for k, ch in enumerate(name):
        acc = (acc * 31 + TABLE[(ord(ch) * 7 + k) % SIDE][(ord(ch) + k * 13) % SIDE]) % 1000003
    return acc


def checksum():
    return sum(sum(row) for row in TABLE) % 1000003
'''

E3_COMMON = '''"""common.py: formatting shared by the command lines."""
import heavy


def fmt(row):
    return f"{row['name']} <{row['email']}> {row['dept']}"


def badge(name):
    return f"badge-{heavy.summary(name):07d}"
'''

E3_LOOKUP = '''"""lookup.py NAME [--full]: the person's row from people.csv; --full adds the badge."""
import csv, sys
from common import badge, fmt


def load(path="people.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    unique = []
    for r in rows:
        if not any(u == r for u in unique):
            unique.append(r)
    return unique


def main(argv):
    full = "--full" in argv
    names = [a for a in argv if a != "--full"]
    if len(names) != 1:
        print("usage: lookup.py NAME [--full]", file=sys.stderr)
        return 2
    name = names[0]
    for r in load():
        if r["name"] == name:
            print(fmt(r) + (f"  {badge(name)}" if full else ""))
            return 0
    print(f"no such person: {name}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''

E3_BUILD = '''"""build.py: write table.sum.txt, the checksum of the pair table (needs all of heavy)."""
import heavy

if __name__ == "__main__":
    with open("table.sum.txt", "w", encoding="utf-8") as f:
        f.write(f"{heavy.SIDE} {heavy.checksum()}\\n")
    print("wrote table.sum.txt")
'''

E3_GEN = '''"""Generate people.csv: 2,000 rows, some duplicated, a few awkward names; deterministic."""
import csv, random, sys

FIRST = ("Alice Bob Carol Dan Eve Frank Grace Heidi Ivan Judy Mallory Niaj Olivia Peggy Rupert Sybil Trent Uma Victor Walter "
         "Xavier Yara Zoë Åsa José Chloé").split()
LAST = "Brown Smith Jones Garcia Müller Quinn Lee Patel Kim Nakamura O'Neil Da Silva Rossi Ivanova Chen".split()
DEPT = "research trading ops data compliance".split()

def main(path="people.csv", rows=2000, seed=1):
    rng = random.Random(seed)
    people = []
    for i in range(rows - 50):
        f, l = rng.choice(FIRST), rng.choice(LAST)
        people.append({"name": f"{f} {l}", "email": f"{f.lower()}.{l.lower().replace(chr(39), '').replace(' ', '')}{i}@example.com",
                       "dept": rng.choice(DEPT)})
    people.insert(0, {"name": "Alice Brown", "email": "<email>", "dept": "research"})
    people.insert(1, {"name": "Zoë Quinn", "email": "<email>", "dept": "data"})
    people += [dict(p) for p in rng.sample(people, 50)]
    rng.shuffle(people)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "email", "dept"])
        w.writeheader()
        w.writerows(people)

if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0] if a else "people.csv", int(a[1]) if len(a) > 1 else 2000, int(a[2]) if len(a) > 2 else 1)
'''

E3_README = '''# people lookup
`python gen.py` writes people.csv. `python lookup.py "Alice Brown"` prints her row (exit 1 and a message on stderr when the
name is unknown; names are matched exactly). `python lookup.py "Alice Brown" --full` adds her badge. `python build.py` writes
table.sum.txt for the nightly job.
'''


def write(folder: Path, files: dict[str, str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8", newline="\n")


def git_fixture(folder: Path) -> None:
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=fixture", "-c", "user.email=<email>", "commit", "-q", "-m", "fixture"]):
        subprocess.run(cmd, cwd=folder, check=True, capture_output=True)


def e1(folder: Path, rows: int, symbols: int) -> None:
    write(folder, {"gen.py": E1_GEN, "report.py": E1_REPORT, "README.md": E1_README, ".gitignore": "__pycache__/\n"})
    subprocess.run([sys.executable, "gen.py", "data.csv", str(rows), str(symbols), "1"], cwd=folder, check=True)
    git_fixture(folder)


def e2(folder: Path, files: int, words: int) -> None:
    write(folder, {"gen.py": E2_GEN, "find.py": E2_FIND, "README.md": E2_README, ".gitignore": "__pycache__/\n"})
    subprocess.run([sys.executable, "gen.py", "notes", str(files), str(words), "1"], cwd=folder, check=True)
    git_fixture(folder)


def e3(folder: Path, rows: int, side: int) -> None:
    write(folder, {"gen.py": E3_GEN, "heavy.py": E3_HEAVY.replace("__SIDE__", str(side)), "common.py": E3_COMMON,
                   "lookup.py": E3_LOOKUP, "build.py": E3_BUILD, "README.md": E3_README, ".gitignore": "__pycache__/\n"})
    subprocess.run([sys.executable, "gen.py", "people.csv", str(rows), "1"], cwd=folder, check=True)
    git_fixture(folder)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("which", choices=["e1", "e2", "e3", "all"])
    ap.add_argument("target", type=Path)
    ap.add_argument("--rows", type=int, default=None)
    ap.add_argument("--symbols", type=int, default=100)
    ap.add_argument("--files", type=int, default=1500)
    ap.add_argument("--words", type=int, default=400)
    ap.add_argument("--side", type=int, default=2000)
    a = ap.parse_args(argv)
    # calibrated 2026-10-12 on the user's PC (4 GB): e1 ~3 s, e2 ~1.9 s, e3 lookup ~2 s (heavy ~1.3 s + dedupe ~0.7 s)
    jobs = {"e1": lambda d: e1(d, a.rows or 150000, a.symbols), "e2": lambda d: e2(d, a.files, a.words),
            "e3": lambda d: e3(d, a.rows or 3000, a.side)}
    if a.which == "all":
        for k, job in jobs.items():
            job(a.target / k)
            print(f"wrote {a.target / k}")
    else:
        jobs[a.which](a.target)
        print(f"wrote {a.target}")
    return 0


if __name__ == "__main__":
    random.seed(0)
    raise SystemExit(main())
