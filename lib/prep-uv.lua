local cmd = require("cmd")
local file = require("file")

local M = {}

local WORD = 65536
local OFFSET = { 0x2325, 0x8422, 0x9CE4, 0xCBF2 }
local PRIME_LOW = 0x01B3

local function warn(msg)
    io.stderr:write("prep-uv: warning: " .. msg .. "\n")
end

local function fail(msg)
    error("prep-uv: " .. msg, 0)
end

local function trim(value)
    return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function normalize_path(path)
    local normalized = trim(path)
    while #normalized > 1 and normalized:sub(-1) == "/" do
        normalized = normalized:sub(1, -2)
    end
    return normalized
end

local function expand_home(path)
    local home = os.getenv("HOME")
    if not home or home == "" then
        return path
    end
    if path == "~" then
        return home
    end
    if path:sub(1, 2) == "~/" then
        return home .. path:sub(2)
    end
    return path
end

local function shell_quote(value)
    return "'" .. tostring(value):gsub("'", [['"'"']]) .. "'"
end

local function command_output(command, cwd)
    local ok, output
    if cwd then
        ok, output = pcall(cmd.exec, command, { cwd = cwd })
    else
        ok, output = pcall(cmd.exec, command)
    end
    if not ok then
        return nil
    end
    output = trim(output or "")
    if output == "" then
        return nil
    end
    return output
end

local function dir_exists(path)
    if not path or path == "" then
        return false
    end
    return command_output("test -d " .. shell_quote(path) .. " && printf ok") == "ok"
end

local function basename(path)
    local normalized = normalize_path(path)
    return normalized:match("([^/]+)$") or normalized
end

local function read_first_line(path)
    local handle = io.open(path, "r")
    if not handle then
        return nil
    end
    local line = handle:read("*l")
    handle:close()
    if not line then
        return nil
    end
    return normalize_path(line)
end

local function write_marker(path, project_root)
    local handle, err = io.open(path, "w")
    if not handle then
        fail("failed to write marker file " .. path .. ": " .. tostring(err))
    end

    local writable_handle = assert(handle)
    writable_handle:write(project_root, "\n")
    writable_handle:close()
end

local function xor_byte(word, byte)
    local low = word % 256
    local high = word - low
    local result = 0
    local bit = 1
    local left = low
    local right = byte

    while bit < 256 do
        local left_bit = left % 2
        local right_bit = right % 2
        if left_bit ~= right_bit then
            result = result + bit
        end
        left = math.floor(left / 2)
        right = math.floor(right / 2)
        bit = bit * 2
    end

    return high + result
end

local function multiply_prime(state)
    local multiplied = {}
    local carry = 0
    for idx = 1, 4 do
        local value = state[idx] * PRIME_LOW + carry
        multiplied[idx] = value % WORD
        carry = math.floor(value / WORD)
    end

    local shifted = {
        0,
        0,
        (state[1] * 256) % WORD,
        (math.floor(state[1] / 256) + (state[2] * 256)) % WORD,
    }

    local result = {}
    carry = 0
    for idx = 1, 4 do
        local value = multiplied[idx] + shifted[idx] + carry
        result[idx] = value % WORD
        carry = math.floor(value / WORD)
    end

    return result
end

local function fnv1a64_hex(input)
    local state = { OFFSET[1], OFFSET[2], OFFSET[3], OFFSET[4] }
    for idx = 1, #input do
        state[1] = xor_byte(state[1], string.byte(input, idx))
        state = multiply_prime(state)
    end
    return string.format("%04x%04x%04x%04x", state[4], state[3], state[2], state[1])
end

local function project_root_from_pwd()
    local pwd_path = os.getenv("PWD") or command_output("pwd")
    if not pwd_path then
        return nil
    end

    local search_root = normalize_path(pwd_path)
    local config_names = {
        "mise.toml",
        ".mise.toml",
        "mise.local.toml",
        ".mise.local.toml",
    }

    while search_root ~= "" do
        for _, config_name in ipairs(config_names) do
            if file.exists(file.join_path(search_root, config_name)) then
                return search_root
            end
        end

        for _, config_path in ipairs({
            file.join_path(search_root, ".mise", "config.toml"),
            file.join_path(search_root, ".config", "mise", "config.toml"),
        }) do
            if file.exists(config_path) then
                return search_root
            end
        end

        if search_root == "/" then
            break
        end

        search_root = search_root:match("^(.*)/[^/]+$") or "/"
    end

    return normalize_path(pwd_path)
end

local function add_candidate(candidates, value)
    if type(value) == "string" and value ~= "" then
        table.insert(candidates, value)
    end
end

local function project_root_from_ctx(ctx)
    local candidates = {}
    add_candidate(candidates, ctx and ctx.config_root)
    add_candidate(candidates, ctx and ctx.project_root)
    add_candidate(candidates, ctx and ctx.configRoot)
    add_candidate(candidates, ctx and ctx.projectRoot)
    add_candidate(candidates, ctx and ctx.options and ctx.options.project_root)
    add_candidate(candidates, os.getenv("MISE_CONFIG_ROOT"))
    add_candidate(candidates, os.getenv("MISE_PROJECT_ROOT"))
    add_candidate(candidates, project_root_from_pwd())

    for _, candidate in ipairs(candidates) do
        local path = normalize_path(expand_home(candidate))
        if path:match("^/") then
            return path
        end
    end

    fail("could not determine project root from mise config context")
end

local function python_path(project_root)
    return command_output("command -v python 2>/dev/null", project_root)
end

local function ensure_uv_on_path(project_root)
    if not command_output("command -v uv 2>/dev/null", project_root) then
        fail("uv must be available on PATH")
    end
end

local function cache_root()
    local override = os.getenv("PREP_UV_CACHE_DIR")
    if override and override ~= "" then
        local resolved = normalize_path(expand_home(override))
        if not dir_exists(resolved) then
            fail("PREP_UV_CACHE_DIR does not exist: " .. resolved)
        end
        return resolved
    end

    local home = os.getenv("HOME")
    if not home or home == "" then
        return nil
    end

    local default_root = file.join_path(home, ".cache", "uv-venvs")
    if dir_exists(default_root) then
        return normalize_path(default_root)
    end

    return nil
end

local function candidate_status(root, venv_dname, project_root)
    local venv_path = file.join_path(root, venv_dname)
    local marker_path = file.join_path(root, venv_dname .. "-root.txt")
    local has_venv = file.exists(venv_path)
    local has_marker = file.exists(marker_path)

    if not has_venv and not has_marker then
        return "available", venv_path, marker_path
    end

    if has_marker then
        local owner = read_first_line(marker_path)
        if owner == project_root then
            return "owned", venv_path, marker_path
        end
        return "collision", venv_path, marker_path
    end

    return "collision", venv_path, marker_path
end

local function choose_venv(root, project_root)
    if not root then
        return {
            centralized = false,
            venv_path = file.join_path(project_root, ".venv"),
        }
    end

    local base = basename(project_root)
    local hash = fnv1a64_hex(project_root)
    local candidates = {
        base,
        base .. "-" .. hash:sub(1, 3),
        base .. "-" .. hash:sub(1, 8),
    }

    for _, venv_dname in ipairs(candidates) do
        local status, venv_path, marker_path = candidate_status(root, venv_dname, project_root)
        if status ~= "collision" then
            return {
                centralized = true,
                venv_path = venv_path,
                marker_path = marker_path,
            }
        end
    end

    fail("could not resolve a collision-free centralized venv path in " .. root)
end

local function ensure_venv(project_root, venv_path, python, marker_path)
    if file.exists(venv_path) then
        return
    end

    local command = "uv venv " .. shell_quote(venv_path) .. " --python " .. shell_quote(python)
    local ok, err = pcall(cmd.exec, command, { cwd = project_root })
    if not ok then
        fail("failed to create virtualenv: " .. tostring(err))
    end

    if marker_path then
        write_marker(marker_path, project_root)
    end
end

function M.resolve(ctx, opts)
    opts = opts or {}

    if RUNTIME and RUNTIME.osType and RUNTIME.osType ~= "linux" then
        fail("Linux is the only supported platform")
    end

    local project_root = project_root_from_ctx(ctx)

    local python = python_path(project_root)
    if not python then
        warn('no Python tool is configured; add `[tools] python = "..."` and retry')
        return {
            env = {},
            paths = {},
        }
    end

    ensure_uv_on_path(project_root)

    local resolved_cache_root = cache_root()
    local chosen = choose_venv(resolved_cache_root, project_root)

    if opts.check_uv_project_environment then
        local existing = os.getenv("UV_PROJECT_ENVIRONMENT")
        if existing and trim(existing) ~= "" then
            local normalized_existing = normalize_path(expand_home(existing))
            if not chosen.centralized or normalized_existing ~= chosen.venv_path then
                fail("UV_PROJECT_ENVIRONMENT is already set; refusing to override a user-supplied value")
            end
        end
    end

    ensure_venv(project_root, chosen.venv_path, python, chosen.marker_path)

    local env_vars = {
        { key = "UV_PYTHON", value = python },
        { key = "VIRTUAL_ENV", value = chosen.venv_path },
    }

    if chosen.centralized then
        table.insert(env_vars, 1, {
            key = "UV_PROJECT_ENVIRONMENT",
            value = chosen.venv_path,
        })
    end

    return {
        env = env_vars,
        paths = { file.join_path(chosen.venv_path, "bin") },
    }
end

return M
