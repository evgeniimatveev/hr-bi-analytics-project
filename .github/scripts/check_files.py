"""Static checks (nothing is executed against a database).

* no secrets file tracked: .env must not be in git (only .env.example)
* every SQL file parses as PostgreSQL (sqlglot)
* every Python script compiles, warnings count as errors
* every exported CSV is non-empty
* every link in the README that points into this repository leads to a file that exists
"""
import glob
import os
import re
import subprocess
import sys
import warnings

import sqlglot
from sqlglot.errors import ParseError, TokenError

problems = []
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True, encoding="utf-8").stdout.splitlines()

if ".env" in tracked:
    problems.append(".env is tracked by git: it must stay local (keep only .env.example)")
if ".env.example" not in tracked:
    problems.append(".env.example is missing")

sql_files = sorted(glob.glob("sql/**/*.sql", recursive=True))
for f in sql_files:
    txt = open(f, encoding="utf-8").read()
    if not txt.strip():
        problems.append(f"{f}: empty file")
        continue
    try:
        sqlglot.parse(txt, read="postgres")
    except (ParseError, TokenError) as exc:
        problems.append(f"{f}: PostgreSQL parse error: {str(exc).splitlines()[0][:120]}")

py_files = sorted(f for f in tracked if f.endswith(".py"))
warnings.simplefilter("error", SyntaxWarning)
for f in py_files:
    try:
        compile(open(f, encoding="utf-8").read(), f, "exec")
    except (SyntaxError, SyntaxWarning) as exc:
        problems.append(f"{f}: does not compile: {exc}")

csvs = sorted(glob.glob("data/*.csv"))
for f in csvs:
    lines = open(f, encoding="utf-8").read().splitlines()
    if len(lines) < 2:
        problems.append(f"{f}: no data rows")

readme = open("README.md", encoding="utf-8").read()
n_links = 0
for url in re.findall(r"\]\(([^)\s]+)\)|src=\"([^\"]+)\"", readme):
    target = url[0] or url[1]
    m = re.match(r"https://github\.com/evgeniimatveev/hr-bi-analytics-project/(?:blob|tree)/main/([^?#]+)", target)
    path = m.group(1) if m else (None if re.match(r"^(https?:|#|mailto:)", target) else target.split("#")[0])
    if path:
        n_links += 1
        if path not in tracked and not os.path.exists(path):
            problems.append(f"README: link to a file that does not exist: {path}")

print(f"Checked {len(sql_files)} SQL files, {len(py_files)} Python files, {len(csvs)} CSV files, {n_links} README links to this repo, {len(problems)} problem(s)")
for p in problems:
    print("FAIL ", p)
sys.exit(1 if problems else 0)
