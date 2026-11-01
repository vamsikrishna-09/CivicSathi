# CivicSathi

An AI-ready civic grievance prototype. Citizens describe a public issue (pothole, garbage, water leak,
blocked drain, broken streetlight), review a suggested category, priority and department, then explicitly
register the complaint to get a tracking ID. A demo admin dashboard updates statuses.

**Prototype only.** Not an official government service or an emergency channel. Complaints are stored in a
local SQLite file and are **not** sent to any municipal authority. Department routing is a recommendation.

## Requirements
Python 3.11+ (Windows, macOS or Linux).

## Setup (Windows PowerShell)
```powershell
cd civicsathi
python -m venv .venv
.venv\Scripts\Activate.ps1      # in cmd.exe use: .venv\Scripts\activate.bat
pip install -r requirements.txt
copy .env.example .env          # optional; demo mode needs no edits
streamlit run app.py
```
macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`, then the same pip/streamlit commands.
If PowerShell blocks activation: `Set-ExecutionPolicy -Scope Process RemoteSigned`.

The app opens at http://localhost:8501 in **DEMO** mode. No API key is required.

## Run the tests
```powershell
pytest
```

## Demo flow
1. **Admin Dashboard** > *Sample data for demos* > *Add sample complaints* (optional, fictional records).
2. **Report an Issue**: enter "There is a large pothole near the main bus stop. Vehicles are swerving to avoid it.",
   location "Near the main bus stop, central area", tick consent, click **Analyse complaint**.
3. Review the result (Pothole / Road Damage, High, Roads & Engineering) and the workflow trace. Nothing is saved yet.
4. Click **Register complaint**. Note the tracking ID (format `CS-YYYY-XXXXXX`) and status *Submitted*.
5. **Admin Dashboard**: filter, open the complaint, set *In Progress*.
6. **Track Complaint**: enter the ID and see *In Progress*.

## Project layout
| File | Purpose |
|---|---|
| `app.py` | Streamlit UI: report, track, admin, about |
| `agents.py` | The three workflow stages and the deterministic demo rules |
| `ai_service.py` | The only place future Gemini calls go (`TODO(MANUAL_AI_INTEGRATION)`) |
| `database.py` | SQLite setup and parameterised queries |
| `models.py` / `utils.py` / `config.py` | Constants and validation / tracking IDs and safe file names / environment settings |
| `tests/` | Rules, database and validation tests |

## Adding AI later
Implement `analyze_issue` and `assess_severity_and_route` in `ai_service.py`, set `AI_INTEGRATION_IMPLEMENTED = True`,
and set `CIVICSATHI_DEMO_MODE=false` and `GEMINI_API_KEY` in `.env` (or the hosting platform's secrets). Their output
is validated in `agents.py`; invalid output or failures fall back to demo rules and are labelled accurately.
A result is labelled `AI` only after a real successful call, and images are never described as analysed unless they were.

## Privacy and clearing data
No names, phones, emails or exact addresses are collected. Data lives in `civicsathi.db` and uploaded photos in `uploads/`.
To clear everything, stop the app and delete both. Both are git-ignored.

## Limitations
Keyword rules are simple and can misclassify. The admin dashboard has no authentication. SQLite suits a local demo,
not heavy traffic. There is no map, notification or municipal integration.

## Deploying (optional)
After local checks, Streamlit Community Cloud works: point it at `app.py` and add secrets in its settings UI.
Never commit `.env` or `.streamlit/secrets.toml`. Hosted file systems are often temporary, so data may reset.

## Troubleshooting
- **`streamlit` not found**: activate the virtual environment, or run `python -m streamlit run app.py`.
- **Port in use**: `streamlit run app.py --server.port 8502`.
- **Database unavailable**: check `CIVICSATHI_DB_PATH` points to a writable folder.
- **Tests cannot import modules**: run `pytest` from the project root (where `pytest.ini` is).
