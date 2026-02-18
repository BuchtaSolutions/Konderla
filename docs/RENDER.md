x# Nasazení na Render (Blueprint)

Projekt je připraven na deploy přes [Render](https://render.com) pomocí Blueprintu (`render.yaml`).

## Co blueprint obsahuje

- **konderla-db** – PostgreSQL (plan free, region Frankfurt), databáze `procurement`
- **konderla-be** – FastAPI backend (Python), složka `konderla-dev-be`
- **konderla-fe** – Next.js frontend (Node), složka `konderla-dev-fe`

## Kroky nasazení

1. **Repozitář na GitHubu/GitLabu**  
   Pushni kód včetně souboru `render.yaml` v kořeni repo.

2. **Render Dashboard**  
   [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint**.

3. **Připojení repo**  
   Vyber repozitář a branch. Render načte `render.yaml` a nabídne vytvoření DB + obou služeb.

4. **Environment variables (po prvním deployi)**  
   - **konderla-be**:  
     - `GOOGLE_API_KEY` – (volitelné) pro Gemini AI. Nastav v **Environment** nebo jako **Secret**.
     - `CORS_ORIGINS` – povolené originy (CORS), oddělené čárkou. Na Renderu nastav na URL frontendu, např. `https://konderla-fe.onrender.com`. (Lokálně stačí výchozí `http://localhost:3000,http://127.0.0.1:3000`.)
   - **konderla-fe**:  
     - `NEXT_PUBLIC_API_URL` – URL backendu, např. `https://konderla-be.onrender.com`  
     (bez koncové lomítko). Bez toho bude frontend volat localhost.

5. **Redeploy frontendu**  
   Po nastavení `NEXT_PUBLIC_API_URL` u frontendu spusť **Manual Deploy** (proměnná se bere při buildu).

## Lokální vs. Render

- **DB**: Lokálně používáš Docker / `docker-compose` (port 5435). Na Renderu vznikne PostgreSQL z blueprintu a `DATABASE_URL` se nastaví automaticky.
- **Backend**: Render nastaví `PORT`; start je `uvicorn main:app --host 0.0.0.0 --port $PORT`.  
  `DATABASE_URL` z Renderu může mít schéma `postgres://` – v kódu ho převádíme na `postgresql://`.
- **Frontend**: Na Renderu musí být nastavené `NEXT_PUBLIC_API_URL` na URL backendu. Lokálně stačí `http://localhost:8000` (výchozí v kódu).

## Migrace a tabulky

Backend při startu volá `models.Base.metadata.create_all(bind=engine)`, takže základní tabulky se vytvoří samy.  
V blueprintu je u backendu `preDeployCommand: python migrate.py` pro případné další migrace (např. sloupce `session_id`).

## Poznámky

- Free plan: služby usínají po nečinnosti, první request může trvat déle.
- Nahrané soubory (uploads) a exporty PDF jsou na ephemeral disku – po redeployi zmizí. Pro trvalé úložiště připoj u backendu **Persistent Disk** nebo ukládej soubory do S3/cloud storage.
