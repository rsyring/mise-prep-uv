from __future__ import annotations

from dataclasses import dataclass, field
import json
from os import environ, getuid, pathsep
from pathlib import Path
import pwd
import subprocess

import pytest


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    def json_data(self) -> dict[str, str]:
        if not self.stdout.strip():
            return {}
        return json.loads(self.stdout)


@dataclass
class Sandbox:
    tmp_path: Path
    repo_root_dpath: Path
    project_python_versions: dict[Path, str | None] = field(default_factory=dict)
    runtime_dpath: Path = field(init=False)
    home_dpath: Path = field(init=False)
    test_projects_dpath: Path = field(init=False)

    def __post_init__(self) -> None:
        self.runtime_dpath = self.tmp_path / 'runtime'
        self.home_dpath = self.runtime_dpath / 'home'
        self.test_projects_dpath = self.runtime_dpath / 'projects'
        for dpath in [
            self.mise_cache_dpath,
            self.mise_config_dpath,
            self.mise_data_dpath,
            self.mise_state_dpath,
            self.test_projects_dpath,
        ]:
            dpath.mkdir(parents=True, exist_ok=True)
        self.global_config_fpath.write_text('')

    @property
    def uv_cache_dpath(self) -> Path:
        return self.home_dpath / '.cache' / 'uv-venvs'

    @property
    def mise_cache_dpath(self) -> Path:
        return self.home_dpath / '.cache' / 'mise'

    @property
    def mise_config_dpath(self) -> Path:
        return self.home_dpath / '.config' / 'mise'

    @property
    def mise_data_dpath(self) -> Path:
        return self.home_dpath / '.local' / 'share' / 'mise'

    @property
    def mise_state_dpath(self) -> Path:
        return self.home_dpath / '.local' / 'state' / 'mise'

    @property
    def global_config_fpath(self) -> Path:
        return self.mise_config_dpath / 'config.toml'

    @property
    def host_home_dpath(self) -> Path:
        return Path(pwd.getpwuid(getuid()).pw_dir)

    @property
    def clean_path(self) -> str:
        return environ.get('__MISE_ORIG_PATH', environ.get('PATH', ''))

    @property
    def host_global_config_fpath(self) -> Path:
        return self.host_home_dpath / '.config' / 'mise' / 'config.toml'

    def python_bin_dpath(self, version: str) -> Path:
        return (
            self.host_home_dpath
            / '.local'
            / 'share'
            / 'mise'
            / 'installs'
            / 'python'
            / version
            / 'bin'
        )

    def base_env(self) -> dict[str, str]:
        trusted_paths = pathsep.join([str(self.repo_root_dpath), str(self.test_projects_dpath)])
        env_vars = {
            'HOME': str(self.home_dpath),
            'MISE_CACHE_DIR': str(self.mise_cache_dpath),
            'MISE_CONFIG_DIR': str(self.mise_config_dpath),
            'MISE_DATA_DIR': str(self.mise_data_dpath),
            'MISE_GLOBAL_CONFIG_FILE': str(self.global_config_fpath),
            'MISE_GLOBAL_CONFIG_ROOT': str(self.home_dpath),
            'MISE_IGNORED_CONFIG_PATHS': str(self.host_global_config_fpath),
            'MISE_STATE_DIR': str(self.mise_state_dpath),
            'MISE_TRUSTED_CONFIG_PATHS': trusted_paths,
            'MISE_USE_VERSIONS_HOST': '0',
            'PATH': self.clean_path,
            'XDG_CACHE_HOME': str(self.home_dpath / '.cache'),
            'XDG_CONFIG_HOME': str(self.home_dpath / '.config'),
            'XDG_DATA_HOME': str(self.home_dpath / '.local' / 'share'),
            'XDG_STATE_HOME': str(self.home_dpath / '.local' / 'state'),
        }
        for key in ['LANG', 'LC_ALL', 'TMPDIR']:
            if value := environ.get(key):
                env_vars[key] = value
        return env_vars

    def run(
        self,
        *args: str,
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> CommandResult:
        work_dpath = cwd or self.runtime_dpath
        env_vars = self.base_env()
        if python_version := self.project_python_versions.get(work_dpath):
            python_bin_dpath = self.python_bin_dpath(python_version)
            env_vars['PATH'] = f'{python_bin_dpath}:{env_vars["PATH"]}'
        env_vars.update(
            {
                'MISE_CONFIG_ROOT': str(work_dpath),
                'MISE_PROJECT_ROOT': str(work_dpath),
                'PWD': str(work_dpath),
            },
        )
        if extra_env:
            env_vars.update(extra_env)
        env_command = ['env', '-i', *[f'{key}={value}' for key, value in env_vars.items()]]
        proc = subprocess.run(
            [*env_command, 'mise', *args],
            capture_output=True,
            check=False,
            cwd=work_dpath,
            text=True,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr)

    def setup_plugin(self) -> None:
        result = self.run('plugins', 'link', 'prep-uv', str(self.repo_root_dpath))
        assert result.returncode == 0, result.stderr
        result = self.run('trust', str(self.test_projects_dpath))
        assert result.returncode == 0, result.stderr

    def write_project(
        self,
        project_root_dpath: Path,
        *,
        python_version: str | None = '3.14',
    ) -> None:
        project_root_dpath.mkdir(parents=True, exist_ok=True)
        self.project_python_versions[project_root_dpath] = python_version
        lines = ['[env]', '_.prep-uv = { tools = true }']
        if python_version is not None:
            lines.extend(['', '[tools]', f'python = "{python_version}"'])
        (project_root_dpath / 'mise.toml').write_text('\n'.join(lines) + '\n')

    def env_json(
        self,
        project_root_dpath: Path,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[CommandResult, dict[str, str]]:
        result = self.run('env', '--json', cwd=project_root_dpath, extra_env=extra_env)
        return result, result.json_data()


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    sandbox = Sandbox(tmp_path=tmp_path, repo_root_dpath=Path(__file__).resolve().parents[1])
    sandbox.setup_plugin()
    return sandbox
