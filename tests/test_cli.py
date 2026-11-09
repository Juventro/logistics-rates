import os
import subprocess
import sys


def test_help_is_available_without_database_credentials():
    env=dict(os.environ)
    env.pop('DATABASE_URL',None)
    result=subprocess.run([sys.executable,'-m','etl.pipeline','--help'],capture_output=True,text=True,env=env)
    assert result.returncode == 0, result.stderr
    assert '--start-date' in result.stdout and '--end-date' in result.stdout and '--as-of' in result.stdout
