.PHONY: report

# Rebuild results/index.html from whatever's already in results/history/,
# without running any tests. Normal test runs rebuild it automatically
# (see conftest.py's pytest_sessionfinish hook) — this is the manual path,
# e.g. after `git pull` brings in new history/*.json from someone else.
report:
	python scripts/build_report.py
