"""Проверка полного и частичного перезапуска на уже загруженном датасете."""
import os
import subprocess
import sys
from datetime import date,timedelta

from etl.db import connect,event


def snapshot(conn):
    result={}
    for table,key in [('core.prices','id'),('core.dq_quarantine_prices','price_id'),
                      ('mart.market_corridor','month,loading_city_gcid,unloading_city_gcid,body_group,weight_category'),
                      ('mart.ml_price_predictions','price_id,body_group,model_name')]:
        # Имена таблиц и ключи заданы в коде, пользовательский SQL сюда не поступает.
        value="to_jsonb(t)-'scored_at'" if table.endswith('ml_price_predictions') else 'to_jsonb(t)'
        result[table]=conn.execute(f"SELECT count(*),md5(string_agg(md5(({value})::text),'' ORDER BY {key})) FROM {table} t").fetchone()
    return result


if __name__=='__main__':
    as_of=date.fromisoformat(os.getenv('AS_OF','2026-10-26'))
    with connect() as conn:
        expected=snapshot(conn)
        assert expected['mart.market_corridor'][0]>0 and expected['mart.ml_price_predictions'][0]>0
        for args in [[],['--start-date',str(as_of-timedelta(weeks=3)),'--end-date',str(as_of)]]:
            subprocess.run([sys.executable,'-m','etl.pipeline',*args],check=True)
            assert snapshot(conn)==expected, f'Rerun changed data: {args}'
        event('repeatability_verified',snapshots=expected)
