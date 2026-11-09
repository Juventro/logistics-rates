TRUNCATE mart.market_corridor;
INSERT INTO mart.market_corridor
WITH observations AS (
    SELECT DISTINCT ON(p.id,date_trunc('month',d.price_date),b.body_group)
           p.id,date_trunc('month',d.price_date)::date AS month,
           p.loading_city_gcid,p.unloading_city_gcid,b.body_group,p.weight_category,
           p.price_rub::float8 AS rate,p.price_rub::float8/p.distance AS km_rate,
           p.organization_id,p.price_type,d.price_date
    FROM core.prices p
    JOIN core.price_months d ON d.price_id=p.id
    JOIN core.price_bodies b ON b.price_id=p.id
    WHERE p.is_fact AND p.price_type IN(1,2,3,4,5,9) AND NOT p.complex AND NOT p.outlier_mark
      AND d.price_date<=current_setting('app.as_of')::date
    ORDER BY p.id,date_trunc('month',d.price_date),b.body_group,d.price_date DESC
), stats AS (
    SELECT month,loading_city_gcid,unloading_city_gcid,body_group,weight_category,
       percentile_cont(0.25) WITHIN GROUP(ORDER BY rate) AS p25_trip,
       percentile_cont(0.5) WITHIN GROUP(ORDER BY rate) AS median_trip,
       percentile_cont(0.75) WITHIN GROUP(ORDER BY rate) AS p75_trip,
       avg(rate) AS avg_trip,
       percentile_cont(0.25) WITHIN GROUP(ORDER BY km_rate) AS p25_km,
       percentile_cont(0.5) WITHIN GROUP(ORDER BY km_rate) AS median_km,
       percentile_cont(0.75) WITHIN GROUP(ORDER BY km_rate) AS p75_km,
       count(DISTINCT id) AS trips_count,
       count(DISTINCT organization_id) FILTER(WHERE price_type IN(3,9)) AS carriers_count,
       CASE WHEN count(*)>=2 THEN stddev_samp(rate)/NULLIF(avg(rate),0) END AS cv_rate,
       max(price_date) AS latest_price_date
    FROM observations GROUP BY 1,2,3,4,5
)
SELECT s.*,
       100*(s.median_trip/NULLIF(m.median_trip,0)-1) AS mom_pct,
       100*(s.median_trip/NULLIF(y.median_trip,0)-1) AS yoy_pct,
       CASE WHEN s.trips_count>=30 AND s.carriers_count>=5
                  AND current_setting('app.as_of')::date-s.latest_price_date<=30 THEN 'HIGH'
            WHEN s.trips_count>=10 THEN 'MEDIUM' ELSE 'LOW_DATA' END
FROM stats s
LEFT JOIN stats m ON m.month=(s.month-INTERVAL '1 month')::date
    AND (m.loading_city_gcid,m.unloading_city_gcid,m.body_group,m.weight_category)=
        (s.loading_city_gcid,s.unloading_city_gcid,s.body_group,s.weight_category)
LEFT JOIN stats y ON y.month=(s.month-INTERVAL '1 year')::date
    AND (y.loading_city_gcid,y.unloading_city_gcid,y.body_group,y.weight_category)=
        (s.loading_city_gcid,s.unloading_city_gcid,s.body_group,s.weight_category);
ANALYZE mart.market_corridor;
