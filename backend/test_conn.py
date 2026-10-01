import os, time
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

print("Connecting...")
t0 = time.time()
try:
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=20)
    print(f"Connected in {time.time()-t0:.1f}s")
    conn.close()
except Exception as e:
    print(f"FAILED after {time.time()-t0:.1f}s: {e}")