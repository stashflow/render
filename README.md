# LUL'S RNG Render Setup

This repo is now ready to run the online backend on Render so school Wi-Fi can use HTTPS (`443`) instead of direct DB sockets.

## Files You Need

- `lulsrng_api.py` -> FastAPI backend (Render web service)
- `requirements.txt` -> Python deps for Render
- `render.yaml` -> Render blueprint config
- `Procfile` -> Start command fallback
- `lulsrng1.1.py` -> game client with API mode support

## 1) Deploy Backend on Render

1. Push this repo to GitHub.
2. In Render, click `New +` -> `Blueprint` (or `Web Service` from repo).
3. Select this repo.
4. If using Web Service setup manually:
   - Environment: `Python`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn lulsrng_api:app --host 0.0.0.0 --port $PORT`
5. Add Render environment variables:
   - `LULSRNG_DB_URL` = your Neon postgres connection string
   - `LULSRNG_API_TOKEN` = a secret token you create (same token used by clients)
6. Deploy.

## 2) Verify API Is Live

After deploy, test:

- `https://YOUR-SERVICE.onrender.com/health`

If token is set, include header:

- `X-API-Token: YOUR_TOKEN`

Expected response includes `db_connected: true`.

## 3) Configure Game Client (school PC)

Set environment variables before launching `lulsrng1.1.py`:

### Windows (PowerShell)

```powershell
$env:LULSRNG_API_BASE="https://YOUR-SERVICE.onrender.com"
$env:LULSRNG_API_TOKEN="YOUR_TOKEN"
python lulsrng1.1.py
```

### Windows (cmd)

```cmd
set LULSRNG_API_BASE=https://YOUR-SERVICE.onrender.com
set LULSRNG_API_TOKEN=YOUR_TOKEN
python lulsrng1.1.py
```

### macOS/Linux

```bash
export LULSRNG_API_BASE="https://YOUR-SERVICE.onrender.com"
export LULSRNG_API_TOKEN="YOUR_TOKEN"
python3 lulsrng1.1.py
```

## 3.1) Direct Run (No Scripts Needed)

`lulsrng1.1.py` now includes built-in API defaults and also reads
`online_client_config.json`, so you can launch it directly:

- Windows: `python lulsrng1.1.py` (or `py lulsrng1.1.py`)
- macOS/Linux: `python3 lulsrng1.1.py`

## 4) Important Notes

- Client API mode is automatic when `LULSRNG_API_BASE` is set.
- If API is unreachable, game falls back to offline behavior.
- Keep `LULSRNG_API_TOKEN` private.

## 5) Quick Troubleshooting

- `db_connected: false` on `/health`:
  - Check `LULSRNG_DB_URL` in Render env.
  - Ensure Neon project is running and credentials are valid.
- Game says offline even with API vars set:
  - Confirm `LULSRNG_API_BASE` and token match exactly.
  - Open the Render URL in browser from school network and verify it responds.
