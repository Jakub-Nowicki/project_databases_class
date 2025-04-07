import psycopg2
from psycopg2 import pool

connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    dbname="project",
    user="postgres",
    password="1234",
    host="localhost",
    port="5432"
)

def get_db_connection():
    """Get a connection from the pool."""
    return connection_pool.getconn()

def release_db_connection(conn):
    """Return a connection to the pool."""
    connection_pool.putconn(conn)