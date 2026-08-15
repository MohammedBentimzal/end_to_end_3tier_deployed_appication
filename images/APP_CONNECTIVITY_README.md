# How Each Backend App Talks to Its Database

This explains, at the code level, how `djangoimg`, `ginimg`, and
`djangomongoimg` each connect to their database — what a "driver" is, what
"ORM" means, and why the Mongo case had to be handled differently.

## First, two concepts used throughout

**Driver**: a small library that knows how to speak a specific database's
network protocol. Postgres, MySQL, and MongoDB each have their own wire
protocol — a driver is what translates "run this query" into the actual
bytes sent over the TCP connection, and translates the response back into
something your code can use. Without the right driver installed, your
language has no way to talk to that specific database at all.

**ORM (Object-Relational Mapper)**: a layer *on top of* a driver that lets
you write Python/Go code instead of raw SQL. Django's ORM is a good
example — you write `connection.cursor().execute("SELECT 1")` or use
Django models, and the ORM translates that into real SQL, sends it through
the driver, and gives you back Python objects. Crucially: **an ORM only
exists for the kind of database it was built for.** Django's ORM was built
for relational (SQL) databases — it has no concept of MongoDB's
document-based model at all.

---

## 1. `djangoimg` — Django + Postgres/MySQL (uses the ORM)

**`config/settings.py`**
```python
DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE"),      # e.g. "django.db.backends.postgresql"
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT"),
    }
}
```
This dictionary is Django's own configuration format — it doesn't connect
to anything by itself. `ENGINE` tells Django **which driver module to load
internally**: `django.db.backends.postgresql` uses the `psycopg2` driver
under the hood; `django.db.backends.mysql` uses `mysqlclient`. Both of
these driver packages are installed via `requirements.txt`. You never call
`psycopg2` or `mysqlclient` directly — Django's ORM does that for you,
based purely on which `ENGINE` string you gave it.

**`backend/views.py` — the actual connection happens here**
```python
from django.db import connection

def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
```
`connection` is Django's ORM connection object — built from the
`DATABASES["default"]` dictionary above. Calling `.cursor()` is the moment
Django actually opens a real network connection to Postgres/MySQL (using
whichever driver `ENGINE` selected), authenticates with `USER`/`PASSWORD`,
and gives you a cursor to run SQL through. `cursor.execute("SELECT 1")`
sends a trivial query — if this succeeds, it proves the app can reach,
authenticate with, and query the database. If the database is down or the
credentials are wrong, this line throws `OperationalError`, which is what
`/health` catches and reports as `"unhealthy"`.

**In short**: you write almost no driver-specific code — you just tell
Django which `ENGINE` to use, and Django's ORM handles opening the
connection, authentication, and running SQL, for either Postgres or MySQL,
using the same `connection.cursor()` code either way.

---

## 2. `ginimg` — Gin, all three databases (uses drivers directly, no ORM)

Go doesn't have anything as "batteries-included" as Django's ORM in this
project — instead, `main.go` uses Go's standard `database/sql` package
directly, plus one driver package per database, and one extra package for
Mongo (which isn't a SQL database at all, so it needs its own client
entirely).

**The drivers, declared at the top of `main.go`:**
```go
import (
    _ "github.com/go-sql-driver/mysql"   // MySQL driver
    _ "github.com/lib/pq"                 // Postgres driver
    "go.mongodb.org/mongo-driver/mongo"   // MongoDB's own official client
)
```
The underscore (`_`) before the MySQL/Postgres imports means "import this
package purely for its side effects" — these drivers register themselves
with Go's `database/sql` package on import, so `sql.Open("postgres", ...)`
or `sql.Open("mysql", ...)` know which driver to actually use, without you
calling the driver package directly anywhere else in the code.

**Postgres connection — built and opened by hand:**
```go
func checkPostgres(cfg dbConfig) error {
    dsn := fmt.Sprintf(
        "host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
        cfg.host, cfg.port, cfg.user, cfg.pass, cfg.name,
    )
    db, err := sql.Open("postgres", dsn)
    ...
    return db.Ping()
}
```
Unlike Django, there's no framework building this connection string for
you — `dsn` (Data Source Name) is manually formatted, containing the host,
port, credentials, and database name, in the exact syntax Postgres's wire
protocol expects. `sql.Open("postgres", dsn)` hands this string to the
`lib/pq` driver, which knows how to parse it and open a real TCP
connection. `db.Ping()` is the equivalent of Django's `cursor.execute
("SELECT 1")` — it forces an actual round trip to the server, which is the
moment the connection and authentication are actually tested.

**MySQL — same idea, different string format:**
```go
dsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s", cfg.user, cfg.pass, cfg.host, cfg.port, cfg.name)
db, err := sql.Open("mysql", dsn)
```
MySQL's DSN format is different from Postgres's (`user:pass@tcp(host:port)/dbname`
instead of `host=... user=...`) — this is exactly why a driver exists: each
database has its own protocol/format, and the driver is what understands
that specific format.

**MongoDB — a completely separate client, not `database/sql` at all:**
```go
func checkMongo(cfg dbConfig) error {
    uri := fmt.Sprintf("mongodb://%s:%s@%s:%s/%s?authSource=admin", ...)
    client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
    ...
    return client.Ping(ctx, nil)
}
```
MongoDB isn't a SQL database, so it can't use Go's `database/sql` package
at all (that package is specifically for SQL-speaking databases). Instead,
MongoDB's official driver (`go.mongodb.org/mongo-driver`) provides its own
separate `mongo.Connect()` client with its own connection URI format
(`mongodb://user:pass@host:port/dbname`) and its own `Ping()` method. This
is structurally the same idea as Postgres/MySQL (build a connection
string, open it, ping it) — just using an entirely different package,
because Mongo speaks a fundamentally different protocol.

**How `main.go` picks which one to use:**
```go
switch cfg.engine {
case "postgres": err = checkPostgres(cfg)
case "mysql":    err = checkMySQL(cfg)
case "mongo":    err = checkMongo(cfg)
}
```
`cfg.engine` comes straight from the `DB_ENGINE` environment variable
Ansible injects. One image, one binary, three completely different
connection functions — the `switch` just picks which one actually runs,
based on what the developer chose.

---

## 3. `djangomongoimg` — Django + Mongo (bypasses the ORM entirely)

This is the one that needed a different approach, and here's exactly why
and how.

**The problem**: Django's `DATABASES["default"]["ENGINE"]` setting only
accepts values like `django.db.backends.postgresql` or
`django.db.backends.mysql` — there is no official
`django.db.backends.mongodb`. Django's ORM was built around SQL concepts
(tables, rows, foreign keys) that don't map cleanly onto MongoDB's
document model. Community packages that try to bridge this gap (like
djongo) exist, but tend to break across Django version upgrades — too
fragile to depend on here.

**The fix — don't use the ORM for Mongo at all:**

`config/settings.py`:
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy",
    }
}
```
`django.db.backends.dummy` is a real, built-in Django backend whose entire
purpose is "let Django finish starting up without actually connecting to
any database." It satisfies Django's requirement that `DATABASES` exists,
without pretending to talk to Mongo through it.

```python
MONGO_HOST = os.getenv("DB_HOST")
MONGO_USER = os.getenv("DB_USER")
MONGO_PASSWORD = os.getenv("DB_PASSWORD")
MONGO_DB_NAME = os.getenv("DB_NAME")
```
Instead, the same environment variables are read as **plain Django
settings**, completely outside the `DATABASES`/ORM system.

`backend/views.py`:
```python
from pymongo import MongoClient

def _get_mongo_client():
    uri = f"mongodb://{settings.MONGO_USER}:{settings.MONGO_PASSWORD}@{settings.MONGO_HOST}:{settings.MONGO_PORT}/{settings.MONGO_DB_NAME}?authSource=admin"
    return MongoClient(uri, serverSelectionTimeoutMS=5000)

def health(request):
    client = _get_mongo_client()
    client.admin.command("ping")
```
`pymongo` is MongoDB's official Python driver — the direct equivalent of
`psycopg2`/`mysqlclient`, except there's no Django ORM layer sitting on
top of it here. `_get_mongo_client()` builds the same style of connection
URI Gin uses, and `client.admin.command("ping")` is the Python/pymongo
equivalent of Go's `client.Ping()` or Django's `cursor.execute("SELECT
1")` — a real round trip that proves the connection and authentication
actually work.

**The key idea**: this view function talks to MongoDB exactly the same
way a plain Python script would, using `pymongo` directly — Django is only
still used here for routing (`/health`, `/api/info`) and serving HTTP,
not for the database interaction itself.

---

## Summary table

| Image | How it connects | Driver/client used | Goes through an ORM? |
|---|---|---|---|
| `djangoimg` | `connection.cursor()` via Django's `DATABASES` config | `psycopg2` (Postgres) or `mysqlclient` (MySQL), selected automatically by `ENGINE` | Yes — Django ORM |
| `ginimg` | Manually built DSN/URI strings, passed to `sql.Open()` or `mongo.Connect()` | `lib/pq`, `go-sql-driver/mysql`, or `mongo-driver`, selected by a `switch` on `DB_ENGINE` | No — Go doesn't have an ORM here, uses drivers directly |
| `djangomongoimg` | `pymongo.MongoClient(uri)`, called directly in the view | `pymongo` | No — Django's ORM is disabled (`dummy` backend); Mongo is accessed exactly like a plain Python script would |
