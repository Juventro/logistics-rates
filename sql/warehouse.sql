CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS core.cities (
    gc_id integer PRIMARY KEY,
    source_id bigint NOT NULL,
    name text NOT NULL,
    region text NOT NULL,
    latitude double precision,
    longitude double precision
);
CREATE TABLE IF NOT EXISTS core.prices (
    id bigint PRIMARY KEY,
    created_at timestamp,
    loading_date date NOT NULL,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    organization_id integer,
    distance double precision NOT NULL CHECK (distance > 0),
    total_weight double precision NOT NULL CHECK (total_weight >= 0),
    total_volume double precision NOT NULL CHECK (total_volume >= 0),
    price_rub numeric(20,2) NOT NULL CHECK (price_rub > 0),
    currency_code varchar(3) NOT NULL,
    nearest_rate_date date,
    weight_category text NOT NULL,
    volume_category text NOT NULL,
    price_type smallint NOT NULL,
    is_fact boolean NOT NULL,
    complex boolean NOT NULL,
    outlier_mark boolean NOT NULL
);
CREATE INDEX IF NOT EXISTS core_prices_loading_idx ON core.prices(loading_date);
CREATE TABLE IF NOT EXISTS core.price_bodies (
    price_id bigint NOT NULL REFERENCES core.prices(id) ON DELETE CASCADE,
    body_group text NOT NULL,
    PRIMARY KEY (price_id, body_group)
);
CREATE TABLE IF NOT EXISTS core.price_months (
    price_id bigint NOT NULL REFERENCES core.prices(id) ON DELETE CASCADE,
    price_date date NOT NULL,
    PRIMARY KEY (price_id, price_date)
);
CREATE INDEX IF NOT EXISTS price_months_date_idx ON core.price_months(price_date);
CREATE TABLE IF NOT EXISTS core.dq_quarantine_prices (
    price_id bigint PRIMARY KEY,
    loading_date date NOT NULL,
    reasons text[] NOT NULL,
    raw_payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS mart.market_corridor (
    month date NOT NULL,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    body_group text NOT NULL,
    weight_category text NOT NULL,
    p25_trip double precision NOT NULL,
    median_trip double precision NOT NULL,
    p75_trip double precision NOT NULL,
    avg_trip double precision NOT NULL,
    p25_km double precision NOT NULL,
    median_km double precision NOT NULL,
    p75_km double precision NOT NULL,
    trips_count bigint NOT NULL,
    carriers_count bigint NOT NULL,
    cv_rate double precision,
    latest_price_date date NOT NULL,
    mom_pct double precision,
    yoy_pct double precision,
    reliability_level text NOT NULL,
    PRIMARY KEY(month,loading_city_gcid,unloading_city_gcid,body_group,weight_category)
);
CREATE TABLE IF NOT EXISTS mart.ml_price_predictions (
    price_id bigint NOT NULL REFERENCES core.prices(id) ON DELETE CASCADE,
    loading_date date NOT NULL,
    loading_city_gcid integer NOT NULL,
    unloading_city_gcid integer NOT NULL,
    body_group text NOT NULL,
    actual_price_rub double precision,
    predicted_price_rub double precision NOT NULL,
    abs_error_rub double precision,
    ape_pct double precision,
    model_name text NOT NULL,
    scored_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(price_id,body_group,model_name)
);
