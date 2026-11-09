import numpy as np
import pandas as pd

CATEGORICAL_FEATURES = ['origin_region','destination_region','body_group','weight_category','volume_category']
NUMERIC_FEATURES = ['distance','total_weight','total_volume','origin_latitude','origin_longitude','destination_latitude','destination_longitude']


def build_features(frame):
    result = pd.DataFrame(index=frame.index)
    for column in NUMERIC_FEATURES:
        result[column] = pd.to_numeric(frame[column],errors='coerce').replace([np.inf,-np.inf],np.nan)
    for column in CATEGORICAL_FEATURES:
        result[column] = frame[column].fillna('Не указан').astype(str)
    dates = pd.to_datetime(frame['loading_date'])
    result['year'] = dates.dt.year
    for name,values,period in [('month',dates.dt.month-1,12),('weekday',dates.dt.dayofweek,7),('yearday',dates.dt.dayofyear-1,365.25)]:
        result[name+'_sin'] = np.sin(2*np.pi*values/period)
        result[name+'_cos'] = np.cos(2*np.pi*values/period)
    return result


def split_history(frame, as_of):
    dates = pd.to_datetime(frame['loading_date'])
    cutoff = pd.Timestamp(as_of)
    test_start = cutoff-pd.Timedelta(weeks=3)
    train_start = cutoff-pd.DateOffset(months=3)
    return (frame[(dates>=train_start)&(dates<test_start)].copy(),
            frame[(dates>=test_start)&(dates<=cutoff)].copy(),
            frame[dates>cutoff].copy())


def prediction_rows(frame, predictions, model_name, as_of):
    result = frame[['price_id','loading_date','loading_city_gcid','unloading_city_gcid','body_group']].copy()
    future = pd.to_datetime(frame['loading_date'])>pd.Timestamp(as_of)
    result['actual_price_rub'] = frame['price_rub'].astype(float).where(~future,np.nan)
    result['predicted_price_rub'] = np.maximum(np.asarray(predictions,dtype=float),0.)
    result['abs_error_rub'] = abs(result.actual_price_rub-result.predicted_price_rub)
    result['ape_pct'] = 100*result.abs_error_rub/result.actual_price_rub
    result['model_name'] = model_name
    return result
