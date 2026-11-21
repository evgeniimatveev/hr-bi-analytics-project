"""Run the project's SQL on a real PostgreSQL and compare every view with the CSV exported from it.

The SQL files must already have been applied (the workflow does that with psql). This script then
  1. reads each of the 6 views and compares it, row by row, with the CSV in data/
  2. re-computes the figures quoted in the README ("Business Questions & Findings")

Environment: PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE (the standard libpq variables).
"""
import glob
import os
import sys

import pandas as pd
import psycopg2

conn = psycopg2.connect()  # reads the PG* environment variables
results = []  # (name, compared, mismatches, examples)


def query(sql):
    return pd.read_sql_query(sql, conn)


def norm(df):
    """Make a view result and a CSV comparable: dates as text, numbers as float, sorted rows."""
    out = pd.DataFrame()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s) or (s.dtype == object and s.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}").all()):
            out[c] = s.astype(str).str[:10]
        elif pd.api.types.is_numeric_dtype(s) or s.dtype == object and pd.to_numeric(s, errors="coerce").notna().all():
            out[c] = pd.to_numeric(s).astype(float).round(2)
        else:
            out[c] = s.astype(str)
    return out.sort_values(list(out.columns)).reset_index(drop=True)


VIEWS = ["employee_full_info", "employee_salary_history", "avg_salary_by_department", "count_by_position", "last_salary_change", "salary_trends"]
for v in VIEWS:
    csv_file = sorted(glob.glob(f"data/{v}_*.csv"))[-1]
    exp = norm(pd.read_csv(csv_file))
    act = norm(query(f"SELECT * FROM {v}"))
    bad = []
    if list(exp.columns) != list(act.columns):
        bad.append(f"columns differ: CSV {list(exp.columns)} vs view {list(act.columns)}")
    elif len(exp) != len(act):
        bad.append(f"row count: CSV {len(exp)} vs view {len(act)}")
    else:
        diff = (exp != act).any(axis=1)
        for i in diff[diff].index[:3]:
            bad.append(f"row {i}: CSV {exp.loc[i].tolist()} vs view {act.loc[i].tolist()}")
        if diff.sum() > 3:
            bad.append(f"... {int(diff.sum())} rows differ")
    results.append((f"view {v}", len(exp), len(bad), bad))

# figures quoted in the README
full = query("SELECT * FROM employee_full_info")
by_dept = full.groupby("dept_name").agg(n=("emp_id", "count"), avg=("salary", "mean"))
company_avg = full.salary.mean()
top_roles = full.groupby("position_name").salary.sum().sort_values(ascending=False)
claims = [
    ("30 employees", len(full), 30),
    ("5 departments", len(by_dept), 5),
    ("largest department is Marketing", by_dept.n.idxmax(), "Marketing"),
    ("Marketing has 7 employees", int(by_dept.loc["Marketing", "n"]), 7),
    ("Marketing is 23% of headcount", round(by_dept.loc["Marketing", "n"] / len(full) * 100), 23),
    ("highest average salary: Sales", by_dept.avg.idxmax(), "Sales"),
    ("Sales average 102,400", round(by_dept.loc["Sales", "avg"]), 102400),
    ("company average is about 87K", round(company_avg / 1000), 87),
    ("Sales is 18% above the company average", round((by_dept.loc["Sales", "avg"] / company_avg - 1) * 100), 18),
    ("minimum salary 58,000", int(full.salary.min()), 58000),
    ("maximum salary 135,000", int(full.salary.max()), 135000),
    ("largest salary budgets: Marketing Analyst, DevOps Engineer, Sales Representative", list(top_roles.index[:3]), ["Marketing Analyst", "DevOps Engineer", "Sales Representative"]),
]
bad = [f"{name}: README says {exp}, data says {act}" for name, act, exp in claims if act != exp]
results.append(("README figures", len(claims), len(bad), bad))

width = max(len(n) for n, *_ in results)
failed = 0
lines = ["| Check | Rows / figures | Mismatches |", "|---|--:|--:|"]
for name, n, nb, ex in results:
    ok = nb == 0 and n > 0
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name:<{width}}  {n:>3} compared, {nb} mismatching")
    for e in ex[:3]:
        print("      ", e)
    lines.append(f"| {name} | {n} | {'✅ 0' if ok else '❌ ' + str(nb)} |")
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write("## Views re-computed in PostgreSQL vs the exported CSV files\n\n" + "\n".join(lines) + "\n")
print(f"\n{len(results) - failed} of {len(results)} checks passed")
sys.exit(1 if failed else 0)
