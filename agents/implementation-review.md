# prep-uv Implementation Review

Review of the current code against `agents/spec-revised.md` and a general code
review. Line references are current as of this review.

## Spec compliance


### Deviations / gaps

1. **Python detection relies on PATH, not an explicit tools check.**
   `python_path` shells out to `command -v python` (`lib/prep-uv.lua:226-228`).
   Per the mise env-plugin docs and `types/mise-plugin.lua`, `MiseEnvCtx`
   exposes only `options`, `config_root`, and `project_root` — there is no
   `ctx.tools`, and the documented pattern for reaching mise-managed tools is
   `tools = true` plus shelling out, so the current approach is the supported
   one. The remaining concern is narrower: `command -v python` will accept any
   `python` on PATH, not strictly one declared in `[tools]`. With `env -i` in
   tests this is fine, but in real shells a system Python could satisfy the
   check. If a stricter guarantee is wanted, the plugin would need to inspect
   the resolved path and verify it lives under the mise installs dir — there
   is no direct `ctx.tools.python.path` API to call.

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
2. Narrow the "no `[tools] python`" check if desired — verify the resolved
   `python` lives under the mise installs directory rather than accepting any
   PATH match. No mise API exposes the tool path directly to env plugins, so
   this would be a heuristic, not an API switch.
3. Drop `project_root_from_pwd` and the ctx alias soup; use the one documented
   `config_root` field (plus a single env-var fallback if needed).
4. Use `dir_exists` (or a shared helper) in `candidate_status`; remove the
   redundant `assert(handle)` in `write_marker`.
5. Trim "Implementation notes" / "Validation notes" from
   `agents/spec-revised.md` so the spec stays a decisions doc, not an
   implementation mirror.


