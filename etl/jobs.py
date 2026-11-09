from datetime import date

from etl.db import LOCK_ID, event, sql_file


def initialize(conn):
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        conn.execute(sql_file('warehouse.sql'))


def run_etl(conn, start_date, end_date, as_of):
    start_date, end_date, as_of = map(lambda d: date.fromisoformat(str(d)), (start_date,end_date,as_of))
    if start_date>end_date:
        raise ValueError('start_date must not exceed end_date')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK_ID,))
        for key,value in [('start_date',start_date),('end_date',end_date),('as_of',as_of)]:
            conn.execute('SELECT set_config(%s,%s,true)', ('app.'+key,str(value)))
        conn.execute(sql_file('clean.sql'))
        conn.execute(sql_file('marts.sql'))
        read = conn.execute('SELECT count(*) FROM pg_temp.batch_prices').fetchone()[0]
        rejected = conn.execute('SELECT count(*) FROM pg_temp.batch_prices WHERE cardinality(reasons)>0').fetchone()[0]
        mart_rows = conn.execute('SELECT count(*) FROM mart.market_corridor').fetchone()[0]
    result = {'read':read,'accepted':read-rejected,'quarantined':rejected,'mart_rows':mart_rows}
    event('etl_complete',start_date=start_date,end_date=end_date,**result)
    return result


def bootstrap(conn, n_prices):
    n_prices = int(n_prices)
    if n_prices<=0:
        raise ValueError('n_prices must be positive')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
        if conn.execute("SELECT to_regclass('raw.prices')").fetchone()[0]:
            event('source_exists',rows=conn.execute('SELECT count(*) FROM raw.prices').fetchone()[0])
            return
        conn.execute('CREATE SCHEMA IF NOT EXISTS raw; SET LOCAL search_path=raw,public')
        conn.execute(sql_file('schema.sql'))
        generator=sql_file('synthetic.sql')
        generator=generator[generator.index('SELECT setseed'):].replace(':n_prices',str(n_prices))
        conn.execute(generator)
    event('source_initialized',rows=n_prices)
