.PHONY: report run-dashboard

# Rebuild results/index.html from whatever's already in results/history/,
# without running any tests. Normal test runs rebuild it automatically
# (see conftest.py's pytest_sessionfinish hook) — this is the manual path,
# e.g. after `git pull` brings in new history/*.json from someone else.
report:
	python scripts/build_report.py

# Launch the local test-runner web app. Must be -m (module), not a direct
# script path — webapp/app.py does `from webapp.catalog import ...`,
# which only resolves if the repo root (not webapp/) is on sys.path, and
# only `python -m webapp.app` (run from the repo root) does that.
run-dashboard:
	python -m webapp.app
