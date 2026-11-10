# MarketMind web app

The Vue 3 front end for MarketMind: the twelve views of the Streamlit dashboard, a runs list, a new-study form and a
live view of a running study with its approval forms. Responsive down to phone width, in light and dark.
It talks only to the FastAPI layer in `../api`.

Run these from the repository root (Node.js 20.19 or newer):

| Command | What it does |
|---|---|
| `npm --prefix frontend install` | Install the dependencies (once) |
| `npm --prefix frontend run build` | Type-check and build into `frontend/dist`, which `python -m api` serves at <http://localhost:8000> |
| `npm --prefix frontend run dev` | Development server on <http://localhost:5173> with hot reload; start `python -m api --reload` beside it |
| `npm --prefix frontend test` | Component tests (Vitest) |
| `npm --prefix frontend run typecheck` | Type-check only (`vue-tsc`) |

Stack: Vite, TypeScript, Vue Router, Pinia, PrimeVue 4.5.5 (pinned: the last MIT-licensed release) and plotly.js
(cartesian bundle). The developer guide (`docs/DEVELOPER_GUIDE.md`, section 12) describes the structure, the API and
how to add a view.
