from __future__ import annotations


class TestPrepUv:
    def test_uses_default_cache_when_present(self, sandbox) -> None:
        sandbox.uv_cache_dpath.mkdir(parents=True)
        project_root_dpath = sandbox.test_projects_dpath / 'alpha'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert env_vars['UV_PROJECT_ENVIRONMENT'] == str(sandbox.uv_cache_dpath / 'alpha')
        assert (sandbox.uv_cache_dpath / 'alpha-root.txt').exists()

    def test_resolves_basename_collisions_with_hash_suffix(self, sandbox) -> None:
        sandbox.uv_cache_dpath.mkdir(parents=True)
        first_root_dpath = sandbox.test_projects_dpath / 'first' / 'shared'
        second_root_dpath = sandbox.test_projects_dpath / 'second' / 'shared'
        sandbox.write_project(first_root_dpath)
        sandbox.write_project(second_root_dpath)

        first_result, _ = sandbox.env_json(first_root_dpath)
        result, env_vars = sandbox.env_json(second_root_dpath)

        assert first_result.returncode == 0, first_result.stderr
        assert result.returncode == 0, result.stderr
        assert env_vars['UV_PROJECT_ENVIRONMENT'].startswith(
            str(sandbox.uv_cache_dpath / 'shared-'),
        )
        assert env_vars['UV_PROJECT_ENVIRONMENT'] != str(sandbox.uv_cache_dpath / 'shared')

    def test_falls_back_to_local_venv_without_central_cache(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'local-mode'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert env_vars['VIRTUAL_ENV'] == str(project_root_dpath / '.venv')
        assert 'UV_PROJECT_ENVIRONMENT' not in env_vars

    def test_warns_and_returns_no_plugin_env_when_python_missing(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'no-python'
        sandbox.write_project(project_root_dpath, python_version=None)

        result, env_vars = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert 'UV_PYTHON' not in env_vars
        assert 'VIRTUAL_ENV' not in env_vars
        assert str(project_root_dpath / '.venv' / 'bin') not in env_vars.get('PATH', '').split(':')
        assert 'no Python tool is configured' in result.stderr

    def test_falls_back_to_project_root_when_config_root_is_missing(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'project-root-fallback'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(
            project_root_dpath,
            extra_env={'MISE_CONFIG_ROOT': ''},
        )

        assert result.returncode == 0, result.stderr
        assert env_vars['VIRTUAL_ENV'] == str(project_root_dpath / '.venv')

    def test_falls_back_to_pwd_when_root_context_is_missing(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'pwd-root-fallback'
        nested_dpath = project_root_dpath / 'src' / 'pkg'
        sandbox.write_project(project_root_dpath)
        nested_dpath.mkdir(parents=True)
        sandbox.project_python_versions[nested_dpath] = '3.14'

        result, env_vars = sandbox.env_json(
            nested_dpath,
            extra_env={
                'MISE_CONFIG_ROOT': '',
                'MISE_PROJECT_ROOT': '',
            },
        )

        assert result.returncode == 0, result.stderr
        assert env_vars['VIRTUAL_ENV'] == str(project_root_dpath / '.venv')

    def test_errors_when_uv_project_environment_is_already_set(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'conflicting-env'
        venv_dpath = project_root_dpath / '.venv'
        sandbox.write_project(project_root_dpath)

        result, _ = sandbox.env_json(
            project_root_dpath,
            extra_env={'UV_PROJECT_ENVIRONMENT': str(sandbox.runtime_dpath / 'already-set')},
        )

        assert result.returncode != 0
        assert 'UV_PROJECT_ENVIRONMENT is already set' in result.stderr
        assert 'VIRTUAL_ENV' not in result.stdout
        assert not venv_dpath.exists()

    def test_allows_matching_uv_project_environment_for_centralized_cache(self, sandbox) -> None:
        sandbox.uv_cache_dpath.mkdir(parents=True)
        project_root_dpath = sandbox.test_projects_dpath / 'matching-env'
        sandbox.write_project(project_root_dpath)
        expected_venv_dpath = sandbox.uv_cache_dpath / 'matching-env'

        result, env_vars = sandbox.env_json(
            project_root_dpath,
            extra_env={'UV_PROJECT_ENVIRONMENT': str(expected_venv_dpath)},
        )

        assert result.returncode == 0, result.stderr
        assert env_vars['UV_PROJECT_ENVIRONMENT'] == str(expected_venv_dpath)

    def test_uses_prep_uv_cache_dir_when_directory_exists(self, sandbox) -> None:
        prep_cache_dpath = sandbox.runtime_dpath / 'prep-cache'
        prep_cache_dpath.mkdir(parents=True)
        project_root_dpath = sandbox.test_projects_dpath / 'custom-cache'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(
            project_root_dpath,
            extra_env={'PREP_UV_CACHE_DIR': str(prep_cache_dpath)},
        )

        assert result.returncode == 0, result.stderr
        assert env_vars['UV_PROJECT_ENVIRONMENT'] == str(prep_cache_dpath / 'custom-cache')

    def test_errors_when_prep_uv_cache_dir_is_missing(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'missing-cache'
        sandbox.write_project(project_root_dpath)

        result, _ = sandbox.env_json(
            project_root_dpath,
            extra_env={'PREP_UV_CACHE_DIR': str(sandbox.runtime_dpath / 'missing-cache')},
        )

        assert result.returncode != 0
        assert 'PREP_UV_CACHE_DIR does not exist' in result.stderr

    def test_creates_virtualenv_automatically_when_missing(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'create-venv'
        venv_dpath = project_root_dpath / '.venv'
        sandbox.write_project(project_root_dpath)

        assert not venv_dpath.exists()
        result, _ = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert venv_dpath.exists()

    def test_adds_exactly_one_venv_bin_directory_to_path(self, sandbox) -> None:
        project_root_dpath = sandbox.test_projects_dpath / 'path-entry'
        venv_bin_dpath = project_root_dpath / '.venv' / 'bin'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert env_vars.get('PATH', '').split(':').count(str(venv_bin_dpath)) == 1

    def test_creates_and_reuses_centralized_marker_files(self, sandbox) -> None:
        sandbox.uv_cache_dpath.mkdir(parents=True)
        project_root_dpath = sandbox.test_projects_dpath / 'reuse-marker'
        marker_fpath = sandbox.uv_cache_dpath / 'reuse-marker-root.txt'
        sandbox.write_project(project_root_dpath)

        first_result, first_env_vars = sandbox.env_json(project_root_dpath)
        second_result, second_env_vars = sandbox.env_json(project_root_dpath)

        assert first_result.returncode == 0, first_result.stderr
        assert second_result.returncode == 0, second_result.stderr
        assert marker_fpath.read_text().strip() == str(project_root_dpath)
        assert second_env_vars['UV_PROJECT_ENVIRONMENT'] == first_env_vars['UV_PROJECT_ENVIRONMENT']

    def test_treats_unmarked_centralized_venv_as_collision(self, sandbox) -> None:
        sandbox.uv_cache_dpath.mkdir(parents=True)
        (sandbox.uv_cache_dpath / 'collision-only').mkdir(parents=True)
        project_root_dpath = sandbox.test_projects_dpath / 'collision-only'
        sandbox.write_project(project_root_dpath)

        result, env_vars = sandbox.env_json(project_root_dpath)

        assert result.returncode == 0, result.stderr
        assert env_vars['UV_PROJECT_ENVIRONMENT'].startswith(
            str(sandbox.uv_cache_dpath / 'collision-only-'),
        )
