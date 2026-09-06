# dsh_si worker

Python numerical worker for the `dsh-signal-integrity` plugin. The TypeScript
side spawns `python -m dsh_si` (through `uv run --project <this dir>`), writes
one JSON request to stdin, and reads one JSON response from stdout. Stderr is
the worker's log channel.

Run the tests:

```sh
uv sync --frozen --group dev
uv run pytest
```
