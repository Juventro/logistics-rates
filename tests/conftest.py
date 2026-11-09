import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL is required for PostgreSQL integration tests')
    with psycopg.connect(url, autocommit=True) as conn:
        name = conn.execute('SELECT current_database()').fetchone()[0]
        if not name.endswith('_test'):
            pytest.fail('Integration tests may only reset a database ending in _test')
        conn.execute('DROP SCHEMA IF EXISTS raw, core, mart CASCADE; CREATE SCHEMA raw; SET search_path=raw,public')
        conn.execute((ROOT/'sql/schema.sql').read_text(encoding='utf-8'))
        conn.execute('SET search_path=public')
        conn.execute("""
            INSERT INTO raw.cities(id,gc_id,name,full_name_local,full_name_gc,latitude,longitude) VALUES
            (1,1001,'Москва','Москва, г. Москва','Москва',55.7,37.6),
            (2,1001,'Дубль','Москва дубль, Москва','Москва',55.7,37.6),
            (3,1002,'Казань','Казань, Татарстан','Казань',55.8,49.1);
            INSERT INTO raw.body_types(id,name,"id_from_1C",std_id) VALUES
            (56,'тент',56,56),(57,'тент бок',57,56),(15,'борт',15,15),(4,'реф',4,4);
            INSERT INTO raw.exchange_rates(num_code,value,setting_date) VALUES
            ('840',90,'2026-09-14'),('840',99,'2026-09-15'),('978',100,'2026-09-14');
        """)
        yield conn


@pytest.fixture
def add_price(db):
    def add(id, **changes):
        from psycopg import sql
        values = dict(id=id, created_at='2026-09-14', updated_at='2026-09-14',
                      loading_date='2026-09-15', end_loading_date='2026-09-15',
                      loading_city_gcid=1001, unloading_city_gcid=1002,
                      distance=100., total_weight=10., total_volume=50., body_type=56,
                      price=2000., currency_code='643', price_type=3, is_fact=True,
                      complex=False, outlier_mark=False, organization_id=101,
                      nearest_rate_date='2026-09-14')
        values.update(changes)
        query = sql.SQL('INSERT INTO raw.prices ({}) VALUES ({})').format(
            sql.SQL(',').join(map(sql.Identifier, values)),
            sql.SQL(',').join(sql.Placeholder() for _ in values))
        db.execute(query, list(values.values()))
        db.execute('INSERT INTO raw.price_dates(price_id,price_date) VALUES(%s,%s)', (id,values['loading_date']))
    return add
