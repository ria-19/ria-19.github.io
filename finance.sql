DROP TABLE IF EXISTS  users;
DROP TABLE IF EXISTS  stockes;

CREATE TABLE users (
    id INTEGER,
    username TEXT NOT NULL,
    hash TEXT NOT NULL,
    cash NUMERIC NOT NULL DEFAULT 10000.00,
    PRIMARY KEY(id)
    );

CREATE UNIQUE INDEX username ON users (username);

CREATE TABLE stockes(
    id INTEGER,
    symbol TEXT NOT NULL,
    shares INTEGER NOT NULL,
    price NUMERIC NOT NULL,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    PRIMARY KEY(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
    );




