import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

from etl.db import connect, event
from etl.jobs import bootstrap, initialize, run_etl


def main():
    parser=argparse.ArgumentParser(description='Загрузка raw/core/mart, обучение и пакетный прогноз тарифов')
    parser.add_argument('--start-date',type=date.fromisoformat)
    parser.add_argument('--end-date',type=date.fromisoformat)
    parser.add_argument('--as-of',type=date.fromisoformat,default=os.getenv('AS_OF','2026-10-26'))
    parser.add_argument('--n-prices',type=int,default=int(os.getenv('N_PRICES','300000')))
    parser.add_argument('--iterations',type=int,default=int(os.getenv('MODEL_ITERATIONS','300')))
    parser.add_argument('--seed',type=int,default=int(os.getenv('RANDOM_SEED','42')))
    parser.add_argument('--artifact-dir',default=os.getenv('ARTIFACT_DIR','artifacts'))
    parser.add_argument('--skip-ml',action='store_true')
    args=parser.parse_args()
    started=time.monotonic()
    with connect() as conn:
        bootstrap(conn,args.n_prices)
        initialize(conn)
        first,last=conn.execute('''
            SELECT min(first_date),max(last_date) FROM (
                SELECT min(loading_date),max(loading_date) FROM raw.prices
                UNION ALL SELECT min(loading_date),max(loading_date) FROM core.prices
                UNION ALL SELECT min(loading_date),max(loading_date) FROM core.dq_quarantine_prices
            ) bounds(first_date,last_date)
        ''').fetchone()
        first,last=first or args.as_of,last or args.as_of
        etl=run_etl(conn,args.start_date or first,args.end_date or last,args.as_of)
        metrics=None
        if not args.skip_ml and conn.execute('SELECT EXISTS(SELECT 1 FROM core.prices)').fetchone()[0]:
            from ml.train import train_and_score
            metrics=train_and_score(conn,args.as_of,args.artifact_dir,args.iterations,args.seed)
        counts={name:conn.execute(query).fetchone()[0] for name,query in {
            'source_rows':'SELECT count(*) FROM raw.prices',
            'core_rows':'SELECT count(*) FROM core.prices',
            'quarantine_rows':'SELECT count(*) FROM core.dq_quarantine_prices',
            'mart_rows':'SELECT count(*) FROM mart.market_corridor',
            'prediction_rows':'SELECT count(*) FROM mart.ml_price_predictions',
        }.items()}
    report={'as_of':str(args.as_of),'etl':etl,'counts':counts,'ml':metrics,'elapsed_seconds':round(time.monotonic()-started,2)}
    directory=Path(args.artifact_dir)
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'run_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    event('pipeline_complete',**report)


if __name__=='__main__':
    main()
