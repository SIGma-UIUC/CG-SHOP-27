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

These commands create `.venv` with Python 3.14.0 and install the dependencies.

Activate the environment using the command for your terminal:

| Terminal | Activation command |
| --- | --- |
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.\.venv\Scripts\Activate.ps1` |
| macOS/Linux bash or zsh | `source .venv/bin/activate` |

Keep your terminal in `src/utils` with the environment activated for all
commands below. Activate it again whenever you open a new terminal.
You can check the selected Python version with `python --version`.

After dependency changes, run `uv sync --python 3.14.0` again.
Run `deactivate` when you are finished to leave the environment.

## Verify an example solution

From `src/utils`, run this as one line:

```sh
python verify.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json
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
python display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json
```

This opens a plot showing the cutter routes and swept area, with uncovered
cells in red. It also prints the longest route's length. Close the plot window
to return to your terminal. Use a matching instance/solution pair for other
examples or your own solver's output.

To save the plot instead of opening a window (also works without a graphical
display), add `--output`:

```sh
python display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json --output ../examples/solution.png
```

Open the PNG in VS Code or an image viewer.

## Animate a solution

With the environment activated, run from `src/utils`:

```sh
python display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json --animate
```

The window shows the cutters moving along their routes and the swept area
growing behind them. Close the window to return to your terminal.

To save a GIF instead of opening a window:

```sh
python display.py ../examples/test_instances1/srpg_246_821_1s3.instance.json ../examples/test_solutions1/srpg_246_821_1s3.solution.json --animate --output ../examples/solution.gif
```

GIF export can take a while. Animated output must have a `.gif` extension;
without `--animate`, the script still produces a static plot.
