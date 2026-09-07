# CG:SHOP 2027; multi-robot lawn mowing

SIGma's group submission for the [CG:SHOP 2027](https://cgshop.ibr.cs.tu-bs.de/competition/cg-shop-2027/) challenge.

## Fork and clone

1. Open [SIGma-UIUC/CG-SHOP-27](https://github.com/SIGma-UIUC/CG-SHOP-27) on GitHub.
2. Click **Fork** to create a copy under your account.
3. Install [Git](https://git-scm.com/downloads), then clone your fork. Replace
   `YOUR-USERNAME` with your GitHub username:

```sh
git clone https://github.com/YOUR-USERNAME/CG-SHOP-27.git
cd CG-SHOP-27
git remote add upstream https://github.com/SIGma-UIUC/CG-SHOP-27.git
```

`origin` points to your fork; `upstream` points to the team's repository.

## Set up the environment

Install a current version of
[uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the
cloned repository's root:

```sh
cd src/utils
uv python install 3.14.0
uv sync --python 3.14.0
```

These commands create `.venv` and install the dependencies. Use stable Python
3.14.0 rather than the old `3.14.0rc1` prerelease, which can fail when importing
Pydantic. If an old standalone installation of uv cannot find stable Python,
run `uv self update` first (or update uv through the tool you installed it with).

Keep your terminal in `src/utils` for all commands below. `uv run` uses the
environment automatically, so activation is not required.

## Included examples

The example instances and solutions are committed under `src/examples/` and
are included in a fresh clone. No separate download is needed. The example
used below is at:

```text
src/
  examples/
    test_instances1/
      srpg_246_821_1s3.instance.json
    test_solutions1/
      srpg_246_821_1s3.solution.json
  utils/
    verify.py
    display.py
    pyproject.toml
```

## Verify an example solution

From `src/utils`, run this as one line:

```sh
uv run --python 3.14.0 verify.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json
```

A feasible solution prints:

```text
=== got 0 errors ===
```

This checks an existing solution against its instance; it does not generate
routes. Replace both filenames with a matching instance/solution pair to check
another example or your own solver's output.

## Display a solution

From `src/utils`, run this as one line:

```sh
uv run --python 3.14.0 display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json
```

This opens a plot showing the cutter routes and swept area, with uncovered
cells in red. It also prints the longest route's length. Close the plot window
to return to your terminal. Use a matching instance/solution pair for other
examples or your own solver's output.

To save the plot instead of opening a window (also works without a graphical
display), add `--output`:

```sh
uv run --python 3.14.0 display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json --output ../examples/solution.png
```

Open the PNG in VS Code or an image viewer. New output files in `src/examples/`
are ignored by Git; the committed example JSON files remain tracked.

## Optional: activate the environment

If you prefer plain `python` commands instead of `uv run`, activate `.venv`
once per terminal session:

| Terminal | Activation command |
| --- | --- |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| macOS/Linux bash or zsh | `source .venv/bin/activate` |

Then use `python verify.py ...` or `python display.py ...` with the examples above. Run
`deactivate` to leave the environment. After dependency changes, run
`uv sync --python 3.14.0` again.
