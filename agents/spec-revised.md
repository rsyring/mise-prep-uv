# Revised Technical Spec: `prep-uv` mise env plugin

## Objective

Implement a mise environment plugin named `prep-uv` that replaces repeated Python/uv environment boilerplate in project `mise.toml` files.

Desired project configuration:

```toml
[env]
_.prep-uv = { tools = true }

[tools]
python = "3.14"
```

The plugin must provide the same effective outcome as the current manual pattern:

```toml
[env]
UV_PROJECT_ENVIRONMENT = '/home/rsyring/.cache/uv-venvs/truth-tooling'
_.python.venv.create = true
_.python.venv.path = '{{ env.UV_PROJECT_ENVIRONMENT }}'
UV_PYTHON = { value = "{{ tools.python.path }}", tools = true }
```

## Scope

This project is a Linux-only mise environment plugin.

The plugin is responsible for:

- determining the correct virtualenv location
- creating the virtualenv when missing
- returning environment variables for activation
- returning the virtualenv `bin` directory for PATH injection
- warning or erroring on invalid/misconfigured usage

The plugin is not responsible for:

- detecting whether the project uses uv via `pyproject.toml` or `uv.lock`
- mutating user config
- supporting non-Linux platforms in this version

## Plugin shape

- Plugin type: mise environment plugin
- Activation: `_.prep-uv = { tools = true }`
- `tools = true` is required so the hook can use mise-managed tools from `PATH`
- The plugin should require `uv` to be available on `PATH`

## Functional behavior

### 1. Python requirement

The plugin requires at least one Python version configured in `[tools]`.

If Python is not configured:

- emit a warning-level message to stderr
- return no env vars
- return no PATH entries

Behavior is all-or-nothing: if required inputs are not available, the plugin should not partially configure the environment.

### 2. Project root

The plugin must determine the project root from mise config context (`config_root`).

This absolute project root path is the source of truth for:

- naming the centralized venv
- collision detection
- registry marker contents

### 3. Venv location selection

The plugin chooses the virtualenv path using the following precedence:

1. If `PREP_UV_CACHE_DIR` is set:
   - if the directory exists, use it as the centralized venv root
   - if the directory does not exist, error clearly and return no env/path
2. If `PREP_UV_CACHE_DIR` is not set and `~/.cache/uv-venvs/` exists, use that as the centralized venv root
3. Otherwise, use a project-local `.venv`

The plugin must not create the centralized cache root automatically.

### 4. Centralized venv naming

When using a centralized cache root:

- start with the basename of the project root directory as `venv_dname`
- intended path is `<cache-dir>/<venv_dname>`

Example:

- project root: `/home/rsyring/projects/my-project`
- initial venv path: `~/.cache/uv-venvs/my-project`

### 5. Registry and collision handling

Centralized venv ownership is tracked with a marker file adjacent to the venv directory:

- marker file path: `<cache-dir>/<venv_dname>-root.txt`
- marker file contents: one line containing the absolute project root path

Behavior:

1. If both the venv directory and marker file are absent, the name is available
2. If the marker file exists and its content matches the current project root, reuse the venv name
3. If the venv directory exists but the marker file is absent, treat that as a collision
4. If the marker file exists and its content differs, a collision exists

The plugin must not auto-adopt or repair an existing centralized venv that lacks a matching marker for the current project. The developer can fix such cases manually.

On collision:

1. compute a stable hash of the absolute project root path using a pure-Lua FNV-1a-64 implementation, hex-encoded
2. first try suffixing the basename with the first 3 hash characters:
   - `<project-name>-<abc>`
3. if that still collides, try the first 8 hash characters
4. if that still collides, raise a clear error explaining the collision

The hash input is the full absolute project root path.

### 6. Venv creation

If the chosen venv does not exist, the plugin must create it during activation.

Creation command:

- required: `uv venv <venv-path> --python <python>`

Do not fall back to `python -m venv`.

If `uv` is not available on `PATH`, the plugin must error clearly and return no env/path (same all-or-nothing behavior as other error conditions).

After successful creation of a centralized venv, the plugin must write/update the matching marker file.

### 7. Returned environment

`<venv-path>` below is the centralized cache venv path in centralized mode and `<project-root>/.venv` in local mode.

If using a centralized cache venv, return:

- `UV_PROJECT_ENVIRONMENT=<venv-path>`
- `UV_PYTHON=<python-path>`
- `VIRTUAL_ENV=<venv-path>`

If using project-local `.venv`, return:

- `UV_PYTHON=<python-path>`
- `VIRTUAL_ENV=<venv-path>`

In the local `.venv` case, do **not** set `UV_PROJECT_ENVIRONMENT`.

### 8. Returned PATH entries

Return exactly one PATH entry:

- `<venv-path>/bin`

This applies to both centralized and local `.venv` modes.

### 9. User-set env conflict handling

If `UV_PROJECT_ENVIRONMENT` is already set by the user environment or config, the plugin must error clearly and return no env/path.

The plugin should not attempt to merge with or override a user-supplied value.

### 10. Missing project files

The plugin should not check for `pyproject.toml` or `uv.lock` before acting.

If the project is invalid for uv, underlying uv errors may pass through to the developer.

## Runtime and implementation constraints

- Implement for the mise env-plugin Lua runtime
- Assume Lua 5.1 compatibility in hook code
- Avoid Lua 5.4-only syntax/features
- Prefer stderr output for warnings/errors when no mise-specific hook channel is available
- Cache plugin results where supported by mise's extended return format

Recommended cache/watch behavior:

- `cacheable = true`
- do not set `watch_files`

## Non-goals

- macOS support
- Windows support
- auto-creation of the centralized cache root
- fallback to non-uv venv creation
- support for partially configured environments after error conditions

## Documentation requirements

Implementation must also update project docs/template metadata:

- replace template defaults in `metadata.lua`
- replace template README content with plugin-specific usage and behavior
- document that users should install/register the plugin as `prep-uv`
- document `PREP_UV_CACHE_DIR`

## Test plan

Use `bats-core` integration tests against a real `mise` binary.

Tests should validate at least:

1. centralized cache dir exists, unique project name
2. centralized cache dir exists, basename collision resolved with hash suffix
3. no centralized cache dir, plugin uses local `.venv`
4. missing `[tools] python` returns no env/path and warns
5. user-set `UV_PROJECT_ENVIRONMENT` errors and returns no env/path
6. `PREP_UV_CACHE_DIR` set to existing dir uses that dir
7. `PREP_UV_CACHE_DIR` set to missing dir errors
8. venv creation occurs automatically when missing
9. PATH contains `<venv>/bin`
10. centralized marker files are created and reused correctly
11. an existing centralized venv directory without a marker is treated as a collision

Tests must isolate cache directories so they do not touch a developer's real `~/.cache/uv-venvs`.

## Acceptance criteria

The spec is satisfied when:

- a project can use only `_.prep-uv = { tools = true }` plus `[tools] python = ...`
- the plugin creates and activates the correct virtualenv automatically
- centralized and local `.venv` modes both work as specified
- collisions are handled deterministically
- error conditions are explicit and do not leave partial env configuration
- bats integration tests cover the required scenarios
