import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from psycopg import sql
from psycopg.rows import dict_row
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

from etl.db import LOCK_ID, event
from ml.features import CATEGORICAL_FEATURES, build_features, prediction_rows, split_history


def train_and_score(conn, as_of, artifact_dir, iterations=300, seed=42):
    as_of = date.fromisoformat(str(as_of))
    model_name = 'catboost_'+as_of.strftime('%Y%m%d')
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK_ID,))
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                SELECT p.id AS price_id,p.loading_date,p.loading_city_gcid,p.unloading_city_gcid,
                       p.price_rub::float8,p.distance,p.total_weight,p.total_volume,p.weight_category,p.volume_category,
                       b.body_group,o.region AS origin_region,d.region AS destination_region,
                       o.latitude AS origin_latitude,o.longitude AS origin_longitude,
                       d.latitude AS destination_latitude,d.longitude AS destination_longitude
                FROM core.prices p JOIN core.price_bodies b ON b.price_id=p.id
                JOIN core.cities o ON o.gc_id=p.loading_city_gcid JOIN core.cities d ON d.gc_id=p.unloading_city_gcid
                WHERE p.is_fact AND p.price_type IN(1,2,3,4,5,9) AND NOT p.complex
                  AND (NOT p.outlier_mark OR p.loading_date>%s)
                ORDER BY p.id,b.body_group
            """,(as_of,))
            frame = pd.DataFrame(cursor.fetchall())
        if frame.empty:
            raise ValueError('No eligible data for training')
        train,test,future = split_history(frame,as_of)
        if len(train)<2 or len(test)<2:
            raise ValueError('Need at least two train and two test observations in the fixed time windows')
        model = CatBoostRegressor(iterations=iterations,depth=6,learning_rate=.08,loss_function='RMSE',
                                  random_seed=seed,thread_count=2,verbose=False,allow_writing_files=False)
        model.fit(build_features(train),train.price_rub,cat_features=CATEGORICAL_FEATURES)
        predicted = np.maximum(model.predict(build_features(test)),0.)
        metrics = dict(model_name=model_name,as_of=str(as_of),seed=seed,iterations=iterations,
                       train_rows=len(train),test_rows=len(test),future_rows=len(future),
                       r2=float(r2_score(test.price_rub,predicted)),
                       mape_pct=float(100*mean_absolute_percentage_error(test.price_rub,predicted)),
                       rmse_rub=float(mean_squared_error(test.price_rub,predicted)**.5),
                       mae_rub=float(mean_absolute_error(test.price_rub,predicted)))
        scoring = pd.concat([test,future],ignore_index=True)
        rows = prediction_rows(scoring,model.predict(build_features(scoring)),model_name,as_of)
        conn.execute('DELETE FROM mart.ml_price_predictions WHERE model_name=%s',(model_name,))
        copy_query = sql.SQL('COPY mart.ml_price_predictions ({}) FROM STDIN').format(sql.SQL(',').join(map(sql.Identifier,rows.columns)))
        clean_rows = rows.astype(object).where(pd.notnull(rows),None)
        with conn.cursor().copy(copy_query) as copy:
            for row in clean_rows.itertuples(index=False,name=None):
                copy.write_row(row)
    directory = Path(artifact_dir)
    directory.mkdir(parents=True,exist_ok=True)
    model.save_model(str(directory/(model_name+'.cbm')))
    (directory/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    event('ml_complete',**metrics)
    return metrics
