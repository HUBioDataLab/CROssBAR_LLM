# Benchmarks

This directory is a separate `uv` project for benchmark and analysis code. It has its own dependencies, virtual environment, and lockfile so benchmark packages do not interfere with the main `crossbar-llm` application environment.

## Project Layout

The main application project lives at the repository root.

The benchmark project lives here:

```text
benchmarks/
├── pyproject.toml
├── uv.lock
├── .venv/
├── biohopr/
└── bioasq/
```

The benchmark project depends on the main package through a local editable dependency:

```toml
crossbar-llm = { path = "..", editable = true }
```

This means benchmark scripts can import `crossbar_llm`, and local changes in the main package are picked up without reinstalling the package.

## First-Time Setup

From the repository root:

```bash
cd benchmarks
uv sync
```

This creates or updates the benchmark virtual environment at:

```text
benchmarks/.venv
```

It installs dependencies from:

```text
benchmarks/pyproject.toml
benchmarks/uv.lock
```

## Reproducing the Locked Environment

For exact reproducibility, use:

```bash
cd benchmarks
uv sync --locked
```

This installs exactly what is recorded in `benchmarks/uv.lock`.

## Running Benchmark Scripts

Always run benchmark scripts from the `benchmarks/` directory using `uv run`.

Example:

```bash
cd benchmarks
uv run python biohopr/biohopr_benchmark_run.py
```

Evaluation example:

```bash
cd benchmarks
uv run python biohopr/evaluate_biohopr_results_with_embedding_similarity.py
```

## Activating the Environment Manually

Usually, prefer `uv run`.

If you want an interactive shell inside the benchmark environment:

```bash
cd benchmarks
source .venv/bin/activate
```
## PyTorch / CUDA

This project currently installs `torch` from the PyTorch CUDA 12.6 wheel index:

```toml
[tool.uv.sources]
torch = { index = "pytorch-cu126" }

[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true
```

Check whether CUDA is available:

```bash
cd benchmarks
uv run python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA not available')"
```

Create a tensor on the GPU:

```bash
cd benchmarks
uv run python -c "import torch; x = torch.tensor([1.0, 2.0], device='cuda'); print(x); print(x.device)"
```

## Installing CPU-Only PyTorch

If you do not have a compatible CUDA GPU, or you want a smaller CPU-only setup, modify `benchmarks/pyproject.toml`.

Keep `torch` and `transformers[torch]` in the dependencies:

```toml
[project]
dependencies = [
    "crossbar-llm",
    "torch",
    "torchmetrics>=1.9.0",
    "transformers[torch]>=5.15.1",
]
```

Then replace the CUDA 12.6 torch source:

```toml
[tool.uv.sources]
crossbar-llm = { path = "..", editable = true }
torch = { index = "pytorch-cu126" }

[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true
```

with the CPU torch source:

```toml
[tool.uv.sources]
crossbar-llm = { path = "..", editable = true }
torch = { index = "pytorch-cpu" }

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

After changing `pyproject.toml`, update the benchmark lockfile and environment:

```bash
cd benchmarks
uv lock
uv sync
```

Check that PyTorch is installed and CUDA is not being used:

```bash
cd benchmarks
uv run python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

For the CPU-only setup, `torch.cuda.is_available()` should print `False`.

## Notes for Contributors

Do not install benchmark-only dependencies into the root project environment.

Use this directory's `uv` project for benchmark work:

```bash
cd benchmarks
uv run python ...
```

The benchmark environment is separate from the main app environment. This is intentional.
