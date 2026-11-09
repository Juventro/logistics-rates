import json
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
LOCK_ID = 20261026


def connect():
    return psycopg.connect(os.getenv('DATABASE_URL',''), autocommit=True)


def event(name, **fields):
    print(json.dumps({'event':name, **fields}, ensure_ascii=False, default=str), flush=True)


def sql_file(name):
    return (ROOT/'sql'/name).read_text(encoding='utf-8')
