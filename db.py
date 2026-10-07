import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    connection = pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),           
        password=os.environ.get('DB_PASSWORD', ''),           
        database=os.environ.get('DB_NAME', 'nepal_travel_db'),
        port=int(os.environ.get('DB_PORT', 3306)),
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection