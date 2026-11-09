from datetime import date

import numpy as np
import pandas as pd

from ml.features import build_features, prediction_rows, split_history


def frame():
    return pd.DataFrame({
        'price_id': [1, 2, 3, 4, 5],
        'loading_date': pd.to_datetime(['2026-07-25', '2026-07-26', '2026-10-04', '2026-10-05', '2026-10-27']),
        'loading_city_gcid': [1001]*5, 'unloading_city_gcid': [1002]*5,
        'origin_region': ['г. Москва']*5, 'destination_region': ['Ленинградская обл.']*5,
        'origin_latitude': [55.7]*5, 'origin_longitude': [37.6]*5,
        'destination_latitude': [59.9]*5, 'destination_longitude': [30.3]*5,
        'distance': [700.0]*5, 'total_weight': [20.0]*5, 'total_volume': [80.0]*5,
        'weight_category': ['FTL']*5, 'volume_category': ['FTL']*5, 'body_group': ['Тент']*5,
        'price_rub': [100000.0]*5, 'price_with_vat': [120000.0]*5,
        'price_group_id': [8]*5, 'avg_price': [100000.0]*5, 'outlier_mark': [False]*5,
    })


def test_features_never_expose_target_or_group_statistics():
    source = frame()
    features = build_features(source)
    assert {'origin_region','destination_region','distance','month_sin','month_cos'} <= set(features)
    assert not {'price_rub','price_with_vat','price_group_id','avg_price','outlier_mark','price_id'} & set(features)
    source['price_rub'] = 999999999.0
    source['avg_price'] = -1
    pd.testing.assert_frame_equal(features, build_features(source))


def test_time_split_has_no_overlap_and_excludes_future():
    train, test, future = split_history(frame(), date(2026,10,26))
    assert train.price_id.tolist() == [2,3]
    assert test.price_id.tolist() == [4]
    assert future.price_id.tolist() == [5]


def test_calendar_encoding_wraps_month_boundary():
    source = pd.concat([frame().iloc[:1]]*2, ignore_index=True)
    source['loading_date'] = pd.to_datetime(['2026-12-31','2027-01-01'])
    features = build_features(source)
    assert abs(features.loc[1,'month_sin']) < 1e-10
    assert abs(features.loc[1,'month_cos']-1) < 1e-10
    assert features.loc[1,'year'] == 2027
    assert np.isfinite(features.select_dtypes('number').to_numpy()).all()


def test_future_prediction_does_not_publish_synthetic_actual_price():
    source = frame().iloc[[3,4]].copy()
    result = prediction_rows(source, [90000.,110000.], 'baseline', date(2026,10,26))
    assert result.iloc[0].actual_price_rub == 100000.
    assert result.iloc[0].abs_error_rub == 10000.
    assert result.iloc[0].ape_pct == 10.
    assert pd.isna(result.iloc[1].actual_price_rub)
    assert pd.isna(result.iloc[1].abs_error_rub)
    assert pd.isna(result.iloc[1].ape_pct)
