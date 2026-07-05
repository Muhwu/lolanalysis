# Packaging

`github-build-workflow.yml` is a GitHub Actions workflow that builds
one-file desktop binaries for Linux/Windows/macOS.

The token this repo is usually pushed with lacks the `workflow` scope, so
the file can't live in `.github/workflows/` via that route. To enable CI
builds, do one of:

1. Add the file at `.github/workflows/build.yml` through the GitHub web UI
   (Add file → paste contents), or
2. `git mv packaging/github-build-workflow.yml .github/workflows/build.yml`
   and push with a token that has the `workflow` scope
   (`gh auth refresh -s workflow`).

Then run it from the Actions tab (workflow_dispatch) or push a `v*` tag;
artifacts appear per-OS on the run page.

Local build (current OS only):

    pip install pyinstaller pywebview
    pyinstaller --onefile --name coach-potato --add-data "static:static" --add-data "VERSION:." desktop.py
