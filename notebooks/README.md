# Notebooks

Experiments backing the thesis figures and metrics. Each notebook pairs with a
chapter, see `documents/roadmap.md` for the mapping.

## Setup

```bash
uv sync --extra analysis
uv run jupyter lab
```

The notebooks read the project's own database, so import data first:

```bash
# Download Online Retail II from the UCI repository, convert to CSV, then:
uv run python -c "
from app.tasks.ingestion import import_online_retail_task
print(import_online_retail_task('/path/to/online_retail_II.csv'))
"
```

Datasets are never committed. Keep them outside the repository or under an
ignored path.

## Convention

Notebooks are committed **with their outputs cleared**. Outputs are large,
they conflict on every rerun, and the figures that matter belong in
`thesis/figures/` where the manuscript can cite them.
