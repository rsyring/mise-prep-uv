# prep-uv Implementation Review

Review of the current code against `agents/spec-revised.md` and a general code
review. Line references are current as of this review.

## Spec compliance

### Matches the spec

- Plugin shape, activation syntax, and metadata name (`prep-uv`).
- Linux-only guard via `RUNTIME.osType` (`lib/prep-uv.lua:329`).
- Venv precedence: `PREP_UV_CACHE_DIR` (must exist) → `~/.cache/uv-venvs/` →
  project-local `.venv` (`cache_root`, `choose_venv`).
- Centralized naming from project-root basename, marker file at
  `<cache>/<name>-root.txt`, ownership by matching absolute root path.
- Collision behavior: unmarked existing venv is treated as collision; retries
  with 3- and 8-char FNV-1a-64 suffix; hard error if still unresolved.
- Pure-Lua FNV-1a-64 implementation (`xor_byte`, `multiply_prime`,
  `fnv1a64_hex`) — no bit library dependency.
- Venv creation uses `uv venv <path> --python <python>`; no `python -m venv`
  fallback; marker written after successful creation.
- Returned env vars match the spec for both centralized and local modes
  (`UV_PROJECT_ENVIRONMENT` only in centralized).
- Single PATH entry `<venv>/bin`.
- Missing Python warns on stderr and returns `env={}, paths={}`.
- `UV_PROJECT_ENVIRONMENT` user-set conflict errors out.
- No `pyproject.toml` / `uv.lock` probing.
- `cacheable = true` on `MiseEnv`; no `watch_files`.
- Docs updated (`README.md`, `metadata.lua`, `mise.toml`).
- pytest integration tests cover all 11 scenarios enumerated in the spec.

### Deviations / gaps

1. **Python detection does not use the mise tools context.**
   `python_path` shells out to `command -v python` (`lib/prep-uv.lua:226-228`).
   The spec and desired pattern reference `{{ tools.python.path }}`. With
   `tools = true` the mise-managed Python is on PATH so this works in practice,
   but:
   - It silently accepts any `python` that happens to be on PATH, not just the
     one declared in `[tools]`. The spec's "at least one Python version
     configured in `[tools]`" check is therefore only approximated.
   - It does not consult `ctx.tools` / equivalent mise API, so the link to the
     configured tool is indirect.
   Consider resolving via the ctx/tools API (see `types/mise-plugin.lua`) and
   erroring only when no python tool entry is present.

2. **`UV_PROJECT_ENVIRONMENT` conflict check is env-hook only.**
   `hooks/mise_path.lua` calls `resolve(ctx)` without
   `check_uv_project_environment=true`. If the user has `UV_PROJECT_ENVIRONMENT`
   set, `MiseEnv` errors but `MisePath` still runs resolution and can return
   PATH entries — violating the "no partial configuration" rule. Either check
   in both hooks or gate `MisePath` on the env-hook outcome.

3. **Project root resolution walks PWD.** The spec says to use `config_root`
   from mise context. `project_root_from_ctx` accepts several ctx keys plus
   `MISE_CONFIG_ROOT` / `MISE_PROJECT_ROOT` env vars and finally a PWD walker
   (`project_root_from_pwd`, `lib/prep-uv.lua:159-197`). The walker is
   speculative and can pick the wrong root if invoked outside a project. Prefer
   failing fast when ctx/env don't supply a root rather than inferring one.

4. **Duplicate warning on missing Python.** Both hooks run `resolve`, and
   `MisePath` is not cacheable, so the "no Python tool is configured" stderr
   warning can be emitted twice per activation. Consider emitting only from
   `MiseEnv`, or short-circuiting `MisePath` when env returned empty.

5. **Venv creation can be triggered from `MisePath`.** Because both hooks call
   `resolve`, and `MisePath` output is not cached, `uv venv` may be invoked by
   whichever hook fires first. Not incorrect (idempotent after first create),
   but surprising; creation semantically belongs to the env hook.

6. **Spec doc hygiene.** `agents/spec-revised.md` still contains
   "Implementation notes" and "Validation notes" sections that restate what the
   code does. Per the loaded agent-specs guidance, specs should not mirror the
   implementation. These sections can be trimmed or removed.

## General code review

### Logic / correctness

- `candidate_status` uses `file.exists(venv_path)` to detect an existing
  centralized venv (`lib/prep-uv.lua:262`). If `file.exists` returns true for
  files as well as directories, a stray regular file at that path would be
  mis-classified. The helper `dir_exists` is already available; use it here for
  consistency with `cache_root`.

- `write_marker` does `if not handle then fail(...) end` and then
  `local writable_handle = assert(handle)` (`lib/prep-uv.lua:91-98`). The
  `assert` is dead after the nil check; keep one or the other.

- `dir_exists` shells out via `test -d` with `cmd.exec` even though the mise
  `file` module likely exposes directory checks. Shelling is fine but it's the
  only place that does so for existence; aligning helpers would reduce surface.

- `python_path` runs `command -v python 2>/dev/null` with `cwd=project_root`.
  `cmd.exec` inherits the caller PATH, so `cwd` has no effect here. Minor, but
  the `cwd` argument is misleading.

- Marker file is written with a trailing newline; `candidate_status` reads the
  first line and trims via `normalize_path`. Consistent, but `normalize_path`
  strips trailing slashes (intended for paths) and happens to also trim
  whitespace via `trim`. Works, though a dedicated "read owner" helper would
  express intent more clearly.

- `fail` uses `error(msg, 0)` which produces a clean message but raises a Lua
  error that mise surfaces as a plugin failure. This is appropriate for the
  spec's hard-error cases, but note that "return no env/path" in the spec is
  satisfied by non-return (mise aborts activation) rather than by returning
  empty tables. Worth confirming that's the intended UX.

### Style / structure

- `lib/prep-uv.lua` is ~375 lines and mixes several concerns (path utils,
  shell helpers, hashing, root resolution, cache/marker logic, hook entry). No
  action required, but splitting hashing into `lib/fnv1a64.lua` would isolate
  the numeric code and make it independently testable.

- `project_root_from_ctx` reads four aliases for the same concept
  (`config_root`, `project_root`, `configRoot`, `projectRoot`) plus
  `ctx.options.project_root`. Pick the documented one from the mise env-plugin
  API and drop the rest; the alias list reads as defensive guessing.

- `OFFSET`, `WORD`, `PRIME_LOW` at module top are fine; a short comment noting
  they encode FNV-1a-64 as four 16-bit words would help future readers.

- `shell_quote`'s nested quoting (`[['"'"']]`) is correct but worth a one-line
  comment since it's easy to mis-edit.

### Tests

- Coverage lines up with the spec's 11 scenarios.
- `test_errors_when_uv_project_environment_is_already_set` only runs `mise env
  --json`; it does not verify that the PATH hook also refuses to add entries.
  Adding a PATH assertion would catch the `MisePath` gap noted above.
- `conftest.Sandbox` is thorough (isolated HOME, XDG, mise dirs, clean PATH).
  Minor: `project_python_versions` is keyed by `Path`; works, but a simple
  dict keyed by string path would avoid pathlib-equality surprises on
  non-normalized inputs.

## Suggested follow-ups (in priority order)

1. Make `MisePath` honor the same error conditions as `MiseEnv` (pass
   `check_uv_project_environment=true`, or have `MisePath` call into the env
   result).
2. Resolve Python from the mise tools context rather than `command -v python`,
   and make the "no `[tools] python`" check explicit.
3. Drop `project_root_from_pwd` and the ctx alias soup; use the one documented
   `config_root` field (plus a single env-var fallback if needed).
4. Use `dir_exists` (or a shared helper) in `candidate_status`; remove the
   redundant `assert(handle)` in `write_marker`.
5. Trim "Implementation notes" / "Validation notes" from
   `agents/spec-revised.md` so the spec stays a decisions doc, not an
   implementation mirror.
