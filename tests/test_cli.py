import os
import subprocess
import sys

import pytest

from etl.jobs import initialize, run_etl


def test_help_is_available_without_database_credentials():
    env=dict(os.environ)
    env.pop('DATABASE_URL',None)
    result=subprocess.run([sys.executable,'-m','etl.pipeline','--help'],capture_output=True,text=True,env=env)
    assert result.returncode == 0, result.stderr
    assert '--start-date' in result.stdout and '--end-date' in result.stdout and '--as-of' in result.stdout


@pytest.mark.parametrize('deleted,invalid', [([1],False),([3],False),([1,2,3],False),([1],True)])
def test_full_cli_refresh_removes_deleted_boundary_records(db,add_price,tmp_path,deleted,invalid):
    for id,day in [(1,'2026-08-01'),(2,'2026-09-01'),(3,'2026-10-01')]:
        add_price(id,loading_date=day,price=0 if invalid and id==1 else 2000)
    initialize(db)
    run_etl(db,'2026-08-01','2026-10-01','2026-10-26')
    db.execute('DELETE FROM raw.prices WHERE id=ANY(%s)',(deleted,))
    result=subprocess.run(
        [sys.executable,'-m','etl.pipeline','--skip-ml','--artifact-dir',str(tmp_path)],
        env={**os.environ,'DATABASE_URL':os.environ['TEST_DATABASE_URL']},
        capture_output=True,text=True,
    )
    assert result.returncode==0, result.stderr
    assert db.execute('SELECT id FROM core.prices ORDER BY id').fetchall()==[(id,) for id in [1,2,3] if id not in deleted]
    assert db.execute('SELECT count(*) FROM core.dq_quarantine_prices').fetchone()[0]==0
