import sqlite3

conn = sqlite3.connect('finance.db')

with open('finance.sql') as f:
	conn.executescript(f.read())

conn.close()