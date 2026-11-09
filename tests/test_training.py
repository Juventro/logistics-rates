from datetime import date

import numpy as np

from etl.jobs import bootstrap, initialize, run_etl
from ml.train import train_and_score


def test_source_bootstrap_is_transactional_and_repeatable(db):
    db.execute('DROP SCHEMA raw CASCADE')
    bootstrap(db,500)
    assert db.execute('SELECT count(*) FROM raw.prices').fetchone()[0] == 500
    assert db.execute('SELECT count(*) FROM raw.cities').fetchone()[0] == 42
    bootstrap(db,500)
    assert db.execute('SELECT count(*) FROM raw.prices').fetchone()[0] == 500
    assert db.execute('SELECT count(*) FROM raw.cities').fetchone()[0] == 42


def test_real_training_and_future_scoring_are_repeatable_and_do_not_use_future_targets(db,add_price,tmp_path):
    for i in range(1,25):
        loading = '2026-08-15' if i<=20 else '2026-10-05' if i<=22 else '2026-11-10'
        add_price(i,loading_date=loading,price=5000+i*200,distance=100+i*10)
    initialize(db)
    run_etl(db,date(2026,7,26),date(2027,1,1),date(2026,10,26))
    metrics=train_and_score(db,date(2026,10,26),tmp_path,iterations=5,seed=42)
    assert all(np.isfinite(metrics[k]) for k in ('r2','mape_pct','rmse_rub','mae_rub'))
    assert metrics['train_rows'] == 20 and metrics['test_rows'] == 2 and metrics['future_rows'] == 2
    select='SELECT price_id,body_group,actual_price_rub,predicted_price_rub,abs_error_rub,ape_pct FROM mart.ml_price_predictions ORDER BY price_id,body_group'
    first=db.execute(select).fetchall()
    assert [row[0] for row in first] == [21,22,23,24]
    assert all(row[2] is None and row[4] is None and row[5] is None for row in first[2:])
    db.execute("UPDATE core.prices SET price_rub=price_rub*99 WHERE loading_date>'2026-10-26'")
    second_metrics=train_and_score(db,date(2026,10,26),tmp_path,iterations=5,seed=42)
    assert db.execute(select).fetchall() == first
    assert metrics == second_metrics
