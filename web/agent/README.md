# Project AI analysis skills

`skills/` follows the Agent Skills `SKILL.md` front matter and supporting-reference format. The backend `app.assistant.service` explicitly loads these two trusted skills and a fixed metrics reference for the project agent. They are not installed into the user's global Codex skills, and they do not grant the model file or shell tools.

- `shrimp-analysis`: dates, pond selection, data definitions, and analysis limits.
- `chart-selection`: ten chart templates and multi-chart combinations; the data tool computes KPIs.

Calculations run in `backend/app/assistant/analytics.py`; the frontend renders an allowlist of components. Editing these skills changes chart selection and response guidance, but cannot bypass backend query limits or add executable code. The agent still responds in Traditional Chinese. See [AI analysis](../docs/ai-analysis.md) for setup and provider configuration.
