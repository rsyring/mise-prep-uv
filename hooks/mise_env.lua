local prep_uv = dofile(RUNTIME.pluginDirPath .. "/lib/prep-uv.lua")

--- Returns environment variables to set when this plugin is active.
--- Documentation: https://mise.jdx.dev/env-plugin-development.html#miseenv-hook
--- @param ctx MiseEnvCtx
--- @return MiseEnvResult
function PLUGIN:MiseEnv(ctx)
    local result = prep_uv.resolve(ctx, { check_uv_project_environment = true })
    return {
        cacheable = true,
        env = result.env,
    }
end
