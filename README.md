# prep-uv

`prep-uv` is a Linux-only [mise](https://mise.jdx.dev) environment plugin that ensures a project's uv virtualenv exists and injects the matching environment variables and `PATH` entry.

## Install

Register the plugin as `prep-uv`:

```bash
mise plugins install prep-uv https://github.com/rsyring/mise-prep-uv.git
```

For local development:

```bash
mise plugins link prep-uv /path/to/mise-prep-uv
```

## Usage

Make sure `uv` is already available on `PATH`, then add the plugin in `[env]` and Python in `[tools]`:

```toml
[env]
_.prep-uv = { tools = true }

[tools]
python = "3.14"
```

`tools = true` is required so the plugin can resolve the mise-managed Python and invoke `uv` from `PATH`.

## Behavior

- If `~/.cache/uv-venvs` exists, or `PREP_UV_CACHE_DIR` is set to an existing directory, the plugin uses a centralized cache and:
    - creates a deterministic venv directory name
    - sets `UV_PROJECT_ENVIRONMENT`
    - detects centralized-name collisions with adjacent `*-root.txt` marker files and resolves them
      with a stable FNV-1a-64 hash suffix
- If no centralized directory exists, falls back to a project-local `.venv`.
- Creates missing virtualenvs with `uv venv <venv-path> --python <python>`.
- Sets `UV_PYTHON`, `VIRTUAL_ENV`, and exactly one PATH entry: `<venv>/bin`.

If `[tools] python` is not configured, the plugin warns and returns no plugin env or `PATH` entries. If `UV_PROJECT_ENVIRONMENT` is already set, or if `PREP_UV_CACHE_DIR` points at a missing directory, the plugin errors and returns no plugin env or `PATH` entries.

## Development

```bash
mise install
mise run lint
mise run test
```

## Tests

Integration coverage is implemented with `pytest` in `test/test_prep_uv.py`. The tests isolate cache and mise directories so they do not touch a developer's real `~/.cache/uv-venvs`.
