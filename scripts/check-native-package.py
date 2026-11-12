#!/usr/bin/env python3
"""Exercise the extracted Lab with no developer tools on its child PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check(archive):
    with tempfile.TemporaryDirectory(prefix='Lab native package ') as directory:
        root = Path(directory)
        package = root / 'download'; package.mkdir()
        with zipfile.ZipFile(archive) as zipped:
            for entry in zipped.infolist():
                path = Path(entry.filename)
                assert not path.is_absolute() and '..' not in path.parts and not stat.S_ISLNK(entry.external_attr >> 16)
                target = package / path; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zipped.read(entry)); target.chmod((entry.external_attr >> 16) & 0o777 or 0o644)
        manifest = json.loads((package / 'lab-package.json').read_text())
        for name, digest in manifest['files'].items():
            assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
        binary = package / ('agent-experiment-lab.exe' if os.name == 'nt' else 'agent-experiment-lab')
        python = package / 'support/python' / ('python.exe' if os.name == 'nt' else 'bin/python3.13')
        empty = root / 'empty'; empty.mkdir()
        env = dict(os.environ, PATH=str(empty), PYTHONPATH=str(root / 'hostile'), PYTHONHOME=str(root / 'hostile'))
        if os.name == 'nt':
            env['PATH'] += os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32')
        def call(*args):
            result = subprocess.run([str(binary), *map(str, args)], env=env, cwd=empty,
                                    text=True, capture_output=True, timeout=60)
            assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
            return result.stdout
        assert 'Repeatable independent-agent' in call('--help')
        fixture = root / 'protocol_fixture.py'
        shutil.copyfile(ROOT / 'tests/fixtures/acp_agent.py', fixture)
        scenario = root / 'scenario.json'; bindings = root / 'bindings.json'
        scenario.write_text(json.dumps({'schema':'agent-experiment-lab.scenario/1', 'label':'Native package protocol fixture',
            'participants':{'one':{'label':'One fixture','kind':'protocol_fixture'}},
            'rooms':{'room':{'members':['one']}},
            'steps':[{'action':'cue','room':'room','text':'A disposable package check'}, {'action':'round','room':'room'}]}))
        bindings.write_text(json.dumps({'schema':'agent-experiment-lab.bindings/1','participants':{'one':{
            'command':[str(python), '-I', '-B', str(fixture), '--home', str(root / 'endpoint')], 'cwd':str(root)}}}))
        assert json.loads(call('validate', scenario, '--bindings', bindings))['valid']
        run = root / 'run'
        assert json.loads(call('run', scenario, '--bindings', bindings, '--output', run))['status'] == 'completed'
        before = (run / 'run.json').read_bytes()
        assert json.loads(call('inspect', run))['status'] == 'completed'
        call('report', run)
        assert (run / 'run.json').read_bytes() == before
        assert (run / 'report.html').is_file()
        # A changed packaged module must be rejected before Python executes it.
        (package / 'support/app/experiment_lab/__init__.py').write_text('raise RuntimeError("must not execute")')
        refused = subprocess.run([str(binary), '--help'], env=env, text=True, capture_output=True, timeout=30)
        assert refused.returncode != 0 and 'checksum mismatch' in refused.stderr
        print(json.dumps({'target':manifest['target'],'source':manifest['source'], 'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'passed':['private Python and official SDK without PATH tools','scenario validation','actual ACP fixture turn',
                      'checkpoint inspection and report','canonical checkpoint unchanged by observation','tampered package rejected'],
            'model_calls':0,'production_operations':0}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('archive', type=Path)
    check(p.parse_args().archive.resolve())
