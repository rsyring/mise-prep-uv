local prep_uv = dofile(RUNTIME.pluginDirPath .. "/lib/prep-uv.lua")

--- Returns PATH entries to prepend when this plugin is active.
--- Documentation: https://mise.jdx.dev/env-plugin-development.html#misepath-hook
--- @param ctx MisePathCtx
--- @return string[]
function PLUGIN:MisePath(ctx)
    local result = prep_uv.resolve(ctx, {
        check_uv_project_environment = true,
        warn_on_missing_python = false,
    })
    return result.paths
end
