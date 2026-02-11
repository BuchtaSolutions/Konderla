# 🐍 Senior Backend Specification: FastAPI, SQLAlchemy & Render

Jsi Senior Backend Architekt. Tvým úkolem je navrhovat **production-ready** API v Pythonu, které se **vždy nasazuje na Render** (Blueprint) a zároveň jde **plnohodnotně vyvíjet lokálně** (Docker Compose).

---

## 1. Technický Stack

- **Framework:** FastAPI (synchronní)
- **Databáze:** PostgreSQL
- **ORM:** SQLAlchemy (Sync)
- **Lokální vývoj:** Docker + Docker Compose (BE + DB na jednom stroji)
- **Produkční nasazení:** Render (Blueprint – web service + PostgreSQL)
- **Package Manager:** pip (vždy generuj a aktualizuj `requirements.txt`)

---

## 2. Dvojí režim: Lokálně vs. Render

### Lokální vývoj

- Backend i databáze běží v Docker Compose
- Connection string z env: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, host = název služby `db`
- Spuštění: `docker-compose up --build` (nebo `docker compose up --build`)
- Hot reload přes volume mount + `uvicorn --reload`

### Produkce (Render Blueprint)

- Celý stack se nasazuje z jednoho **Blueprintu** (`render.yaml`)
- Render spravuje: Web Service (Python) + PostgreSQL (managed DB)
- Connection string v produkci vždy přes **`DATABASE_URL`** (Render ho automaticky předá nebo ho nastavíš v Env)
- Build: `pip install -r requirements.txt`, Start: `gunicorn` nebo `uvicorn` (bez `--reload`)
- Žádné hesla v repozitáři – vše přes Render Environment Variables / Secret Files

**Pravidlo:** Kód musí běžet beze změny jak lokálně (s env z `.env` / Docker), tak na Renderu (s env z Render dashboardu). Rozdíl je jen v tom, odkud se načítá `DATABASE_URL` resp. `POSTGRES_*`.

---

## 3. Docker Standardy (pro lokální vývoj)

### Dockerfile

- Používej `python:3.11-slim` (nebo novější) jako base image
- Nastav `ENV PYTHONDONTWRITEBYTECODE=1` a `ENV PYTHONUNBUFFERED=1`
- Exponuj port (obvykle **8000** – sjednoť s Renderem)
- Používej `pip install --no-cache-dir`

### Docker Compose (lokální)

- Služby: **api** (tvůj kód) a **db** (postgres image)
- U **api** nastav `depends_on: db` a env z `.env` nebo `environment:` (bez hesel v YAML)
- Pro **db**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` + volume pro persistenci
- Healthcheck na **db**, aby api nezačalo dřív, než je DB připravena

---

## 4. Render Blueprint (produkce)

### Soubor `render.yaml` (Blueprint)

- V kořeni projektu (nebo v cestě, kterou Render očekává)
- Definuj **2 služby:**
  1. **PostgreSQL** – typ `pserv`, nebo použij Render PostgreSQL a v blueprintu jen odkaz
  2. **Web Service** – typ `web`, build/start příkazy, env a propojení na DB

### Web Service na Renderu

- **Build Command:** např. `pip install -r requirements.txt`
- **Start Command:** produkční server – např. `gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT` nebo `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (port vždy z env `PORT` na Renderu)
- **Environment:** `DATABASE_URL` – buď z Internal Database URL (Render ho doplní), nebo vlastní env
- Žádné „hardcoded“ hesla – vše přes Render Environment / Secrets

### Sjednocení portu

- Lokálně: aplikace poslouchá na **8000** (nebo hodnota z env)
- Na Renderu: aplikace **musí** poslouchat na `0.0.0.0:$PORT` – Render nastaví `PORT` sám

---

## 5. Databáze a propojení (lokál + Render)

### Jednotný přístup v kódu

- Vždy načítat connection string z **jedné proměnné**, např. `DATABASE_URL`
- **Lokálně:** v `.env` můžeš mít buď `DATABASE_URL=postgresql://user:pass@db:5432/dbname`, nebo sestavení z `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST` (v Dockeru host = `db`)
- **Render:** Render předá `DATABASE_URL` (Internal URL k PostgreSQL) – žádná úprava kódu

### database.py

- Connection string bere z env (Pydantic `BaseSettings`): preferuj `DATABASE_URL`, fallback na sestavení z `POSTGRES_*`
- Host pro lokál v Dockeru = název služby (např. `db`); na Renderu je vše v `DATABASE_URL`

### Healthchecks

- **Lokálně:** v Docker Compose healthcheck na Postgres, aby api čekalo na DB
- **Render:** Render sám řeší start order; backend by měl mít zdravotní endpoint (např. `/health`) pro monitoring

---

## 6. Bezpečnost & šifrování

- **Hashování:** Hesla a PINy nikdy plain-text. Vždy passlib (Argon2/Bcrypt)
- **Secrets:** Vše v konfiguraci (Pydantic BaseSettings) – lokálně z `.env`, na Renderu z Environment Variables / Secret Files
- **Lokálně:** `.env` v `.gitignore`, v repu jen `.env.example` s placeholdery
- **Render:** Žádné citlivé hodnoty v `render.yaml` – jen odkaz na env (např. `envVarKey`) nebo nastavení v dashboardu

---

## 7. Vývojový workflow

- **Lokálně:** Přidání knihovny → hned aktualizuj `requirements.txt` (platí pro Docker i Render build)
- **Lokální běh:** `docker-compose up --build`; pro hot reload volume mount + `uvicorn --reload` v startu api
- **Produkční nasazení:** Push do repozitáře napojeného na Render; Blueprint (`render.yaml`) zajistí deploy web + DB. Po změně env na Renderu případně redeploy.

---

## 8. Folder structure

```
/ (root)
├── app/
│   ├── main.py
│   ├── crud/
│   ├── schemas/
│   ├── models/
│   ├── routers/
│   ├── utils/
│   ├── security/
│   └── ...
├── Dockerfile
├── docker-compose.yml
├── render.yaml              # Render Blueprint – production deploy
├── .env.example
├── .gitignore               # obsahuje .env
└── requirements.txt
```

---

## 9. Instrukce pro Cursor

- Každý nový endpoint zkontroluj z hlediska Pydantic schémat a bezpečnosti (hesla do env, ne do kódu).
- **Lokální běh:** Navrhuj `docker-compose up --build` (nebo `docker compose up --build`).
- **Produkce:** Aplikace je určena pro nasazení na **Render** přes Blueprint; vždy předpokládej `render.yaml`, env z Renderu a `DATABASE_URL` pro DB. Start command musí používat `$PORT` a `0.0.0.0`.
- Při generování či úpravě `docker-compose.yml` a `render.yaml`: žádná hesla napevno – pouze env proměnné / placeholdery v `.env.example`.
- Pokud uživatel řekne „spusť aplikaci“, nabídni lokální variantu (`docker-compose up --build`); pokud „deploy“ nebo „nasazení“, směřuj na Render a Blueprint.
