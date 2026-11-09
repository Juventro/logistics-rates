from datetime import date

import psycopg
import pytest

from etl.jobs import initialize, run_etl

START, END, ASOF = date(2023,1,1), date(2027,12,31), date(2026,10,26)


def run(db):
    initialize(db)
    return run_etl(db, START, END, ASOF)


@pytest.mark.parametrize('changes,reason', [
    ({'price':0},'INVALID_PRICE'), ({'price':1000},'INVALID_RUB_PRICE'),
    ({'distance':0},'INVALID_DISTANCE'), ({'total_weight':-1},'INVALID_WEIGHT'),
    ({'total_volume':-1},'INVALID_VOLUME'), ({'loading_city_gcid':9999},'MISSING_CITY'),
    ({'currency_code':'840','nearest_rate_date':None},'MISSING_FX'),
    ({'currency_code':'999'},'UNSUPPORTED_CURRENCY'),
    ({'price':float('nan')},'INVALID_PRICE'),
])
def test_bad_rows_are_quarantined(db,add_price,changes,reason):
    add_price(1,**changes)
    run(db)
    assert db.execute('SELECT count(*) FROM core.prices').fetchone()[0] == 0
    assert reason in db.execute('SELECT reasons FROM core.dq_quarantine_prices WHERE price_id=1').fetchone()[0]


def test_fx_uses_saved_date_not_loading_date_and_rub_threshold_is_currency_specific(db,add_price):
    add_price(1,price=33,currency_code='840')
    run(db)
    assert db.execute('SELECT price_rub FROM core.prices').fetchone()[0] == 2970


def test_foreign_amount_rounding_to_zero_goes_to_quarantine(db,add_price):
    add_price(1,price=.000001,currency_code='840')
    run(db)
    assert db.execute('SELECT count(*) FROM core.prices').fetchone()[0] == 0
    assert 'INVALID_NORMALIZED_PRICE' in db.execute('SELECT reasons FROM core.dq_quarantine_prices').fetchone()[0]


@pytest.mark.parametrize('weight,volume,want_weight,want_volume', [
    (9.96,120,'FTL','FTL'),(30,0,'G20T','OTH'),(2.5,120.1,'5T','OTH'),(.49,50,'L5T','FTL'),(.4,50,'OTH','FTL'),
])
def test_category_boundaries_use_rounded_weight(db,add_price,weight,volume,want_weight,want_volume):
    add_price(1,total_weight=weight,total_volume=volume)
    run(db)
    assert db.execute('SELECT weight_category,volume_category FROM core.prices').fetchone() == (want_weight,want_volume)


def test_cities_body_groups_and_months_do_not_multiply_one_observation(db,add_price):
    add_price(1)
    db.execute('INSERT INTO raw.price_body_types(price_id,body_type_id) VALUES(1,56),(1,57),(1,15)')
    db.execute("INSERT INTO raw.price_dates(price_id,price_date) VALUES(1,'2026-10-15'),(1,'2026-11-15')")
    run(db)
    assert db.execute('SELECT count(*) FROM core.cities').fetchone()[0] == 2
    assert db.execute('SELECT count(*) FROM core.price_bodies').fetchone()[0] == 2
    rows=db.execute('SELECT month,body_group,trips_count FROM mart.market_corridor ORDER BY month,body_group').fetchall()
    assert len(rows) == 4
    assert all(row[2] == 1 for row in rows)
    assert max(row[0] for row in rows) == date(2026,10,1)


def test_market_percentiles_counts_filters_and_null_calendar_gaps(db,add_price):
    for id,price,pt,org in [(1,2000,3,101),(2,4000,3,101),(3,6000,9,102),(4,8000,2,103)]:
        add_price(id,price=price,price_type=pt,organization_id=org)
    add_price(5,price=100000,outlier_mark=True)
    add_price(6,price=100000,price_type=6,is_fact=False)
    add_price(7,price=100000,complex=True)
    add_price(8,price=2500,loading_date='2026-07-15')
    add_price(9,price=2500,loading_date='2025-09-15')
    run(db)
    row=db.execute("SELECT p25_trip,median_trip,p75_trip,avg_trip,median_km,trips_count,carriers_count,mom_pct,yoy_pct,reliability_level FROM mart.market_corridor WHERE month='2026-09-01'").fetchone()
    assert row[:7] == (3500,5000,6500,5000,50,4,2)
    assert row[7] is None
    assert row[8] == 100
    assert row[9] == 'LOW_DATA'


def test_reload_updates_quarantine_removes_deleted_rows_and_is_idempotent(db,add_price):
    add_price(1)
    run(db)
    before=db.execute('SELECT row_to_json(m) FROM mart.market_corridor m').fetchall()
    run_etl(db,START,END,ASOF)
    assert db.execute('SELECT row_to_json(m) FROM mart.market_corridor m').fetchall() == before
    db.execute('UPDATE raw.prices SET price=100 WHERE id=1')
    run_etl(db,START,END,ASOF)
    assert db.execute('SELECT count(*) FROM core.prices').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM core.dq_quarantine_prices').fetchone()[0] == 1
    db.execute('UPDATE raw.prices SET price=3000 WHERE id=1')
    run_etl(db,START,END,ASOF)
    assert db.execute('SELECT count(*) FROM core.dq_quarantine_prices').fetchone()[0] == 0
    db.execute('DELETE FROM raw.prices WHERE id=1')
    run_etl(db,START,END,ASOF)
    assert db.execute('SELECT count(*) FROM core.prices').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM mart.market_corridor').fetchone()[0] == 0


def test_failed_reload_rolls_back_the_previous_window(db,add_price):
    add_price(1)
    run(db)
    db.execute("""CREATE FUNCTION core.reject_new() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.id=2 THEN RAISE EXCEPTION 'injected failure'; END IF; RETURN NEW; END $$;
        CREATE TRIGGER reject_new BEFORE INSERT ON core.prices FOR EACH ROW EXECUTE FUNCTION core.reject_new();""")
    db.execute('UPDATE raw.prices SET price=9000 WHERE id=1')
    add_price(2)
    with pytest.raises(psycopg.errors.RaiseException):
        run_etl(db,START,END,ASOF)
    assert db.execute('SELECT id,price_rub FROM core.prices').fetchall() == [(1,2000)]
