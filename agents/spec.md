# Project Spec

## Plugin template

This repo is a clone of: https://github.com/jdx/mise-env-plugin-template


## Objective

We are writing a plugin for mise to take care of some boilerplate that is
common when we use mise with our python/uv projects.

This is what mise.toml often looks like:

```toml
[env]
# Python venv
UV_PROJECT_ENVIRONMENT = '/home/rsyring/.cache/uv-venvs/truth-tooling'
_.python.venv.create = true
_.python.venv.path = '{{ env.UV_PROJECT_ENVIRONMENT }}'
UV_PYTHON = { value = "{{ tools.python.path }}", tools = true }

[tools]
python = "3.14"
```

We want it to look like:

```toml
[env]
_.prep-uv = { tools = true }

[tools]
python = "3.14"
```

When finished, we should be able to get rid of this file in our projects (which use coppy):

https://github.com/level12/coppy/blob/main/template/tasks/mise-uv-init.py


## References

https://mise.jdx.dev/plugins.html
https://mise.jdx.dev/env-plugin-development.html
https://github.com/level12/coppy/discussions/66#discussioncomment-15976006 h
https://github.com/level12/coppy/issues/93


## Tests

The project should have thorough integration tests.

Research best practices on how to test a project like this plugin.


## Open Questions

> What exact behavior should `_.prep-uv = { tools = true }` expand to beyond the example shown?

Nothing.  The four env settings shown in the example above are what we would set.

> How should `UV_PROJECT_ENVIRONMENT` be derived so it is stable and portable across machines?

The plugin should check for `~/.cache/uv-venvs/` (expand ~) and:

- IF set, deterministically create a venv directory
- NOT set, use a project local .venv

Note: in the case of NOT, we:

- DO NOT set: UV_PROJECT_ENVIRONMENT
- `_.python.venv.path = '.venv'`

> Should the plugin assume `python` is already declared in `[tools]`, or should it validate/fail clearly when it is missing?

If it's not set, it should output a warning level message indicating the plugin requires a setting at least one python version in [tools].

> What files should the plugin look for to decide whether prep behavior should apply (for example `pyproject.toml` and/or `uv.lock`)?

It shouldn't.  If the user has installed the plugin and activated in mise.toml, we can assume
they want to use it.  If they don't have a pyproject.toml, uv will error, and we can just pass
that error through to the dev.

> What platforms/shells need to be supported and tested?

Assume Linux.  I don't think shells matter as this is a mise plugin.  Correct me if I'm wrong on that.

> Remaining question: what exact deterministic naming rule should map a project to `~/.cache/uv-venvs/<name>`?

- Start by: use the name of the project's root folder, i.e. $venv_dname
- Create the directory in `~/.cache/uv-venvs/$venv_dname`
    - Add a text file with a single line that is the full path to the project directory
    - i.e. `_project-root.txt` would contain something like `/home/rsyring/projects/my-project`
- Subsequent runs would find the directory present, check `_project-root.txt` and if it's the same as the project, us it.
- If project root is not the same, we have a collission.  Do a fast hash of the full project root and, take the first five chars, and use that for $venv_dname.  Which would give us something like:
    `$vevnv_dname = $project_dname-$hash_part`

My reasoning on this is most venvs won't clash.  In that case, the venv name is clean.

But we still have a way to detect a clash and, in that case, put the hash on the end.  It's
not as nice as a clean name, but handles the clash.

> which stable hash function to use for the collision suffix

uv is working on this, see what they use for hashing in this PR: https://github.com/astral-sh/uv/pull/18214/changes


> what to do if the 5-char hashed name also collides

Since we use the entire path to the project root as the source for the hash, it shouldn't be possible.  Since a directory hash should be unique.

Keep taking additional characters from the hash until it's unique?


## Review: Questions / Comments / Concerns

### Feasibility of the target `mise.toml` shape — resolved via research

Confirmed from mise docs (plugins overview + env-plugin development):

- **No plugin type of any kind** (environment, tool, or backend) can inject mise config directives like `_.python.venv.create` / `_.python.venv.path` into the user's configuration. Plugins return data (env vars, PATH entries, tool versions); they do not mutate mise's own `[env]` schema.
- Environment plugins are the right fit: they return env vars (`MiseEnv`) and PATH entries (`MisePath`), which is exactly what `_.python.venv.*` expands to under the hood (prepend `<venv>/bin` to PATH, set `VIRTUAL_ENV`, optionally create the venv).
- The `tools = true` module-level flag on `_.prep-uv = { tools = true }` is what makes this workable: when set, mise-managed tools (python, uv) are on `PATH` while our hooks run, and `cmd.exec()` inherits that environment. So the plugin can shell out to `uv venv` / `python` itself.
- Plugins have access to Lua modules `cmd`, `file`, `env`, `strings`, `json`, `http` (see docs). Enough to create directories, write marker files, run `uv venv`, and resolve the python path.

**Decision:** stay with an environment plugin. Replace the three `_.python.venv.*`/`UV_PYTHON{tools=true}` lines from the "after" example by having the plugin itself perform the equivalent work during `MiseEnv`/`MisePath`.

Revised contract for what the plugin does on activation (with `_.prep-uv = { tools = true }`):

1. Resolve the python executable (from `PATH` inside the hook, since `tools = true` makes mise's python available).
2. Determine the project root from mise's `config_root` (https://mise.jdx.dev/environments/#config-root). Exact access mechanism from a Lua env hook is TBD — likely via `MISE_CONFIG_ROOT` in the inherited env, otherwise `cmd.exec("mise config ls")` or equivalent; resolved during implementation.
3. If `[tools] python` isn't declared, emit a warning and return no env/path.
4. Compute the venv path per the cache-dir rules already in the spec (using `config_root`'s basename for `$venv_dname`).
5. If the venv directory does not exist, create it (`uv venv <path> --python <python>` preferred; fall back to `python -m venv` if uv isn't on PATH).
6. From `MiseEnv` return: `UV_PROJECT_ENVIRONMENT=<venv>`, `UV_PYTHON=<python>`, `VIRTUAL_ENV=<venv>`.
7. From `MisePath` return: `<venv>/bin`.
8. Use the extended `MiseEnv` return format with `cacheable = true` and `watch_files = { <config_root>/mise.toml, <config_root>/pyproject.toml }` so we're not shelling out on every prompt.

### Notes (not blocking)

- **Lua runtime version.** The doc states env-plugin Lua is **5.1** ("version 5.1 at the moment"), but this repo's `mise.toml` pins `lua = "5.4"` (used by the LSP/linter). Not a blocker; we should avoid 5.4-only syntax (`//`, `<const>`) in hooks and pin lua-language-server to 5.1 via `.luarc.json` `"runtime.version": "Lua 5.1"` so the linter catches regressions.
- **Plugin name.** Repo is `mise-prep-uv`; the target config uses `_.prep-uv`. The installed plugin name is whatever `mise plugin install` registers it as (CLI arg), so users will need to install with name `prep-uv`. Worth calling out in the README.
- **Platforms.** Linux-only is fine. Shells are irrelevant for an env plugin (mise handles shell-specific exports). If macOS ever matters, honor `XDG_CACHE_HOME` instead of hard-coding `~/.cache`.
- **Template cleanup.** `metadata.lua` still has template defaults (`name = "my-env-plugin"`, author, repo URL) and README is still the template README. Both need updating as part of implementation.

### Open Questions

Remaining items I need decisions on before implementation:

1. **Venv creation inside the hook.** mise's `_.python.venv.create = true` creates on activation, so there's precedent. OK to have the plugin run `uv venv` from `MiseEnv` the first time the venv is missing?

Yes

2. **uv requirement.** Prefer `uv venv` for creation. OK to hard-require `uv` on `PATH` (it's a uv-focused plugin) and error with a clear message if missing, or should we silently fall back to `python -m venv`?

Require uv.  No point in using this plugin if uv isn't being used.

3. **Auto-create `~/.cache/uv-venvs/`?** Current spec implies no (only use the shared cache when the dir already exists). Confirm.

confirmed.  Only use the cache dir if it exists.  People who don't want centralized venvs won't
have it defined.

4. **Respect user-set `UV_PROJECT_ENVIRONMENT`.** If the user has already set it (in their own `[env]` or the shell), should the plugin defer and set nothing? I'd argue yes.

Throw an error.  They shouldn't be setting that and trying to activate our plugin.

5. **Marker file location.** Putting `_project-root.txt` *inside* the venv risks conflicts with uv's own files / `uv sync --reinstall`. Propose moving the marker outside the venv — e.g. `~/.cache/uv-venvs/.registry/<venv_dname>.txt` or sibling `~/.cache/uv-venvs/<venv_dname>.project-root`. Confirm.

Ok, use `~/.cache/uv-venvs/.prep-uv`

6. **Hash function.** Lua 5.1 has no crypto stdlib. Propose pure-Lua FNV-1a-64 hex over the absolute `config_root` path, take the first 5 chars. Shelling out to `sha256sum` on every shell activation is wasteful. Agree?

Agree.  But take the first three chars and if there is a conflict, take the first 8.

7. **Collision termination.** "Keep taking additional characters" needs a stop rule and implies rescanning sibling markers on every activation. Propose: on collision, extend to 8 chars and stop; if that still collides, error with a clear message. Agree?

After that, if still a conflict, good error that explains what is going on.

8. **Warning channel when `[tools] python` is missing.** Propose: `print()` to stderr from the hook, and return empty env/path so we don't pollute the user's environment with half-configured `UV_*`. Agree, or do you want half-config with a warning?

I don't know what the standard is for mise hooks on warn/error.  Do that.  If unsure, print() to
stderr is fine.

We would not want to set any env vars if we have errors.  It should be all or nothing.

9. **Test framework.** Bats-core driving a real `mise` binary against fixture projects (asserting on `mise env --json`) — the jdx convention — or pytest+subprocess for parity with your other tooling? Either way, fixture scenarios: (a) shared cache + unique name, (b) shared cache + colliding name, (c) no shared cache (→ `.venv`), (d) missing `[tools] python`, (e) user-set `UV_PROJECT_ENVIRONMENT`.

This isn't a python project so we probably shouldn't use pytest?

We could have ~/.cache/uv-venvs/ come from an environmet variable and just have that be the default.  That would give flexibility for the actual path and give us a way to change it during
testing so we aren't messing with the dev's actual venvs directory.

### Follow-up Questions

A few small things raised by the previous answers:

10. **Marker layout under `.prep-uv`.** Interpreting "use `~/.cache/uv-venvs/.prep-uv`" as a **directory** owned by the plugin, with one marker file per venv: `~/.cache/uv-venvs/.prep-uv/<venv_dname>` containing the absolute `config_root` on a single line. Collision detection reads the matching marker file in that dir. Confirm?

Or, we could have `~/.cache/uv-venvs/.prep-uv/<venv_dname>` be the marker file itself.  So:

`~/.cache/uv-venvs/.prep-uv/<venv_dname>.txt`

11. **Cache-dir override env var name.** Propose `PREP_UV_CACHE_DIR`. If set and the directory exists → use it. If set and missing → error (don't silently fall back). If unset → check `~/.cache/uv-venvs/` as today. Agree on the name and the "set but missing = error" behavior?

Agreed

12. **Test framework choice.** Ruling out pytest. The two realistic options for a Lua mise plugin are **bats-core** (shell-level integration tests against a real `mise` binary — what jdx's own plugin repos use) or **busted** (Lua-native unit tests, but harder to drive mise end-to-end). I recommend bats-core for the integration tests the spec calls for. Confirm?

Confirmed

13. **`.venv` fallback and `UV_PROJECT_ENVIRONMENT`.** Earlier in the spec, the fallback rule says: when not using the shared cache dir, do **not** set `UV_PROJECT_ENVIRONMENT` and use local `.venv`. But the revised plugin contract later says `MiseEnv` should return `UV_PROJECT_ENVIRONMENT=<venv>`. Which behavior do you want in the `.venv` fallback case?

UV_PROJECT_ENVIRONMENT should ONLY be set when a centralized directory exists.

If not, we still need to set VIRTUAL_ENV, which is what `_.python.venv.path` sets behind the
scenes (you should confirm that).
