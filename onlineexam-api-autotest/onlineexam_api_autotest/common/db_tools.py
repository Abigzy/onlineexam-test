# -*- coding: utf-8 -*-
"""数据库工具（对齐 IHRM 的 common/db_tools.py）。

用途仅限"造数/校验的最后一公里"：
  * 把 `deadline_at` 改到过去，稳定复现超时交卷（不 sleep）；
  * 核对接口返回值是否真的落库。
业务结论优先从接口取，查库只做补充证据。

连接参数从被测项目的 `.env` 读取（默认 D:/OnlineExam/.env），
避免把口令写进测试代码；可用 EXAM_ENV_FILE 指定其他文件。
"""
import os

import pymysql


def _load_env(path: str) -> dict:
    data = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


_ENV = _load_env(os.environ.get("EXAM_ENV_FILE", "D:/OnlineExam/.env"))


class DbTools(object):
    @classmethod
    def conn_db(cls):
        return pymysql.connect(
            host=os.environ.get("DB_HOST") or _ENV.get("DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("DB_PORT") or _ENV.get("DB_PORT", 3306)),
            user=os.environ.get("DB_USER") or _ENV.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD") or _ENV.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME") or _ENV.get("DB_NAME", "online_exam"),
            charset=_ENV.get("DB_CHARSET", "utf8"),
            cursorclass=pymysql.cursors.DictCursor,
        )

    @classmethod
    def query_db(cls, sql: str, args=None):
        conn = cls.conn_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, args or ())
                return cursor.fetchall()
        finally:
            conn.close()

    @classmethod
    def db_uid(cls, sql: str, args=None):
        """写操作：提交并返回影响行数。"""
        conn = cls.conn_db()
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, args or ())
            conn.commit()
            return affected
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


if __name__ == "__main__":
    print(DbTools.query_db("SELECT COUNT(*) AS c FROM users"))
