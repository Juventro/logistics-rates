DELETE FROM core.cities;
INSERT INTO core.cities
SELECT DISTINCT ON(gc_id) gc_id,id,name,
       COALESCE(NULLIF(btrim(split_part(full_name_local,',',2)),''),'Не указан'),latitude,longitude
FROM raw.cities ORDER BY gc_id,id;

DROP TABLE IF EXISTS pg_temp.batch_prices;
CREATE TEMP TABLE batch_prices ON COMMIT DROP AS
WITH rates AS (
    SELECT DISTINCT ON(num_code,setting_date) *
    FROM raw.exchange_rates ORDER BY num_code,setting_date,id
)
SELECT p.*,
       to_jsonb(p) AS raw_payload,
       round(p.price::numeric * CASE WHEN p.currency_code='643' THEN 1 ELSE fx.value::numeric END,2) AS normalized_price_rub,
       COALESCE(NULLIF(btrim(p.weight_category),''), CASE
         WHEN round(p.total_weight::numeric,1)>=30 THEN 'G20T'
         WHEN round(p.total_weight::numeric,1)>=10 THEN 'FTL'
         WHEN round(p.total_weight::numeric,1)>=5 THEN '10T'
         WHEN round(p.total_weight::numeric,1)>=2.5 THEN '5T'
         WHEN round(p.total_weight::numeric,1)>=0.5 THEN 'L5T' ELSE 'OTH' END) AS normalized_weight_category,
       COALESCE(NULLIF(btrim(p.volume_category),''), CASE WHEN p.total_volume>0 AND p.total_volume<=120 THEN 'FTL' ELSE 'OTH' END) AS normalized_volume_category,
       array_remove(ARRAY[
         CASE WHEN NOT(p.price>0 AND p.price<'Infinity'::float8) THEN 'INVALID_PRICE' END,
         CASE WHEN p.currency_code='643' AND p.price<=1000 THEN 'INVALID_RUB_PRICE' END,
         CASE WHEN round(p.price::numeric*CASE WHEN p.currency_code='643' THEN 1 ELSE fx.value::numeric END,2)<=0 THEN 'INVALID_NORMALIZED_PRICE' END,
         CASE WHEN NOT(p.distance>0 AND p.distance<'Infinity'::float8) THEN 'INVALID_DISTANCE' END,
         CASE WHEN NOT(p.total_weight>=0 AND p.total_weight<'Infinity'::float8) THEN 'INVALID_WEIGHT' END,
         CASE WHEN NOT(p.total_volume>=0 AND p.total_volume<'Infinity'::float8) THEN 'INVALID_VOLUME' END,
         CASE WHEN c1.gc_id IS NULL OR c2.gc_id IS NULL THEN 'MISSING_CITY' END,
         CASE WHEN p.currency_code NOT IN('643','840','978') THEN 'UNSUPPORTED_CURRENCY' END,
         CASE WHEN p.currency_code IN('840','978') AND (fx.value IS NULL OR NOT(fx.value>0 AND fx.value<'Infinity'::float8)) THEN 'MISSING_FX' END
       ],NULL) AS reasons
FROM raw.prices p
LEFT JOIN core.cities c1 ON c1.gc_id=p.loading_city_gcid
LEFT JOIN core.cities c2 ON c2.gc_id=p.unloading_city_gcid
LEFT JOIN rates fx ON fx.num_code=p.currency_code AND fx.setting_date=p.nearest_rate_date
WHERE p.loading_date BETWEEN current_setting('app.start_date')::date AND current_setting('app.end_date')::date;

DELETE FROM core.prices
WHERE loading_date BETWEEN current_setting('app.start_date')::date AND current_setting('app.end_date')::date
   OR id IN(SELECT id FROM batch_prices);
DELETE FROM core.dq_quarantine_prices
WHERE loading_date BETWEEN current_setting('app.start_date')::date AND current_setting('app.end_date')::date
   OR price_id IN(SELECT id FROM batch_prices);

INSERT INTO core.dq_quarantine_prices
SELECT id,loading_date,reasons,raw_payload FROM batch_prices WHERE cardinality(reasons)>0;
INSERT INTO core.prices
SELECT id,created_at,loading_date,loading_city_gcid,unloading_city_gcid,organization_id,
       distance,total_weight,total_volume,normalized_price_rub,currency_code,nearest_rate_date,
       normalized_weight_category,normalized_volume_category,price_type,is_fact,complex,outlier_mark
FROM batch_prices WHERE cardinality(reasons)=0;

INSERT INTO core.price_bodies
SELECT DISTINCT p.id,CASE
    WHEN COALESCE(b.std_id,x.body_type_id,p.body_type) IN(56,57,58,59,60,61) THEN 'Тент'
    WHEN COALESCE(b.std_id,x.body_type_id,p.body_type) IN(4,46,47,48) THEN 'Рефрижератор'
    WHEN COALESCE(b.std_id,x.body_type_id,p.body_type)=2 THEN 'Изотерм'
    WHEN COALESCE(b.std_id,x.body_type_id,p.body_type) IN(1,15) THEN 'Борт'
    WHEN COALESCE(x.body_type_id,p.body_type) IS NULL THEN 'Не указан' ELSE 'Прочие' END
FROM batch_prices p
JOIN core.prices c ON c.id=p.id
LEFT JOIN raw.price_body_types x ON x.price_id=p.id
LEFT JOIN raw.body_types b ON b.id=COALESCE(x.body_type_id,p.body_type);
INSERT INTO core.price_months
SELECT d.price_id,d.price_date FROM raw.price_dates d
JOIN batch_prices p ON p.id=d.price_id JOIN core.prices c ON c.id=p.id;
ANALYZE core.prices;
ANALYZE core.price_bodies;
ANALYZE core.price_months;
