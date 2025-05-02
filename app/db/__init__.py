import psycopg2
from psycopg2 import pool

# create a connection pool for postgresql database with minimum 1 and maximum 20 connections
connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    dbname="project",
    user="postgres",
    password="1234",
    host="localhost",
    port="5432"
)

def get_db_connection():
    return connection_pool.getconn()

def release_db_connection(conn):
    connection_pool.putconn(conn)