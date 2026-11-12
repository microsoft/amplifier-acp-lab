#!/usr/bin/env python3
"""Release builder only: package Lab, its official SDK and private Python."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
from native_binary import inspect

ROOT = Path(__file__).resolve().parents[1]
SDK = 'agent-client-protocol @ git+https://github.com/agentclientprotocol/python-sdk.git@9853d8b514d6340000bcbd01ec07808436db80cf'
spec = importlib.util.spec_from_file_location('python_support', ROOT / 'scripts/vendor/python/python_support.py')
support = importlib.util.module_from_spec(spec); spec.loader.exec_module(support)


def package(binary, target, cache, output, source):
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('An exact component source revision is required')
    _, asset = support.asset_for(target)
    family = 'windows' if 'windows' in target else 'macos' if 'apple' in target else 'linux'
    architecture = 'aarch64' if target.startswith('aarch64') else 'x86_64'
    binary_metadata = inspect(binary.read_bytes(), family + '-' + architecture)
    if family == 'windows' and not binary_metadata['standalone_vc_runtime']:
        raise ValueError('The native launcher must bundle its C runtime')
    if not binary.is_file() or binary.is_symlink():
        raise ValueError('Use the compiled native launcher')
    with tempfile.TemporaryDirectory(prefix='lab-native-') as directory:
        root = Path(directory)
        python = root / 'support/python'
        distribution = support.prepare(target, cache, python)
        interpreter = python / asset['executable']
        app = root / 'support/app'; app.mkdir()
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        # All native dependency wheels are pinned by version and distributor hash.
        subprocess.run([str(interpreter), '-I', '-B', '-m', 'pip', 'install', '--no-compile',
                        '--only-binary=:all:', '--require-hashes', '--target', str(app),
                        '-r', str(ROOT / 'scripts/package-requirements.txt')], check=True, env=env)
        subprocess.run([str(interpreter), '-I', '-B', '-m', 'pip', 'install', '--no-compile', '--no-deps',
                        '--target', str(app), '--report', str(root / 'sdk-provenance.json'), SDK], check=True, env=env)
        report = json.loads((root / 'sdk-provenance.json').read_text())
        sdk = next(row for row in report['install'] if row['metadata']['name'] == 'agent-client-protocol')
        if sdk['download_info']['vcs_info']['commit_id'] != '9853d8b514d6340000bcbd01ec07808436db80cf':
            raise ValueError('Official SDK source identity changed')
        shutil.copytree(ROOT / 'experiment_lab', app / 'experiment_lab', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(ROOT / 'scripts/launch.py', root / 'support/launch.py')
        for name in ('LICENSE', 'README.md'):
            shutil.copyfile(ROOT / name, root / name)
        shutil.copyfile(ROOT / 'scripts/package-requirements.txt', root / 'DEPENDENCIES.txt')
        shutil.copyfile(ROOT / 'pyproject.toml', root / 'PROJECT.toml')
        name = 'agent-experiment-lab.exe' if 'windows' in target else 'agent-experiment-lab'
        shutil.copyfile(binary, root / name); (root / name).chmod(0o755)
        # Package imports must not mutate its frozen inventory on first launch.
        for pyc in root.rglob('*.pyc'): pyc.unlink()
        version = re.search(r'__version__ = "([^"]+)"', (ROOT / 'experiment_lab/__init__.py').read_text())[1]
        files = {p.relative_to(root).as_posix(): support.digest(p) for p in root.rglob('*') if p.is_file()}
        manifest = {'schema': 1, 'component': 'agent-experiment-lab', 'version': version,
                    'target': target, 'source': source, 'python': distribution,
                    'official_sdk_commit': '9853d8b514d6340000bcbd01ec07808436db80cf', 'files': files}
        (root / 'lab-package.json').write_text(json.dumps(manifest, indent=2) + '\n')
        output.mkdir(parents=True, exist_ok=True)
        archive = output / f'agent-experiment-lab-{version}-{target}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            for p in sorted(root.rglob('*')):
                if not p.is_file(): continue
                entry = zipfile.ZipInfo(p.relative_to(root).as_posix())
                entry.create_system = 3
                entry.external_attr = (0o100755 if p.stat().st_mode & 0o111 else 0o100644) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                zipped.writestr(entry, p.read_bytes())
        archive.with_name(archive.name + '.sha256').write_text(support.digest(archive) + '  ' + archive.name + '\n')
        archive.with_name(archive.name + '.json').write_text(json.dumps({**manifest, 'files': None,
            'filename': archive.name, 'sha256': support.digest(archive), 'signed_or_notarized': False}, indent=2) + '\n')
        return archive


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', required=True)
    a = p.parse_args()
    print(package(a.binary, a.target, a.cache, a.output, a.source))
