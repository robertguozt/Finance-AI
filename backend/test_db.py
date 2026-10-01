import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # 读取 .env,把里面的变量塞进环境
DATABASE_URL = os.environ.get("DATABASE_URL")

print("正在连接 Neon ...")
conn = psycopg2.connect(DATABASE_URL)   # ① 拨号
cur = conn.cursor()                     # ② 拿游标

cur.execute("SELECT version();")        # ③ 问一句:你是什么版本?
result = cur.fetchone()                 # 取回一行结果
print("连接成功!数据库版本:")
print(result[0])

cur.close()                             # ④ 挂电话
conn.close()