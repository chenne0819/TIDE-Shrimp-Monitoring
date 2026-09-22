# Monorepo publication — 2026-09-22

The publication checkout contains `tracking/` (the completed monitoring integration) and `web/` (the frontend, API, worker, database configuration and AI assistant). It retains the original tracking repository history and the fork relationship. The original local development folders were not moved or modified.

## Publication changes

- Moved the upstream tree into `tracking/` in a separate commit, then applied the completed water/biometric integration.
- Added the web platform and changed the analyzer default to `../tracking`, resolved relative to the web application root.
- Translated maintained documentation and comments to English while retaining Traditional Chinese UI text, AI answers and query examples. The original upstream README remains an explicitly identified archive.
- Excluded personal environment files, authentication, secrets, runtime folders, new model weights and recordings. Removed the local demo video and its extracted thumbnail from the publication; synthetic demo results do not claim to contain a playable real video.
- Used GitHub noreply author metadata. Inspected the Git index before publication rather than relying on ignore patterns alone.

## Validation

The following checks ran against this publication checkout on Windows:

| Check | Result |
| --- | --- |
| `tracking/`: `python -m pytest tests -q` | 86 passed, using separately supplied local water/biometric models kept out of Git |
| `web/backend/`: `python -m pytest tests -q` | 290 passed, including two relocated/default analyzer path cases; two existing dependency deprecation warnings |
| `web/frontend/`: `npm test` | 150 passed, including two checks that synthetic demos expose no private media URLs or video/image requests |
| `web/frontend/`: `npm run lint` | Passed |
| `web/frontend/`: clean `npm ci --prefer-offline --no-audit --no-fund` | Passed; repaired missing/inconsistent optional transitive dependency entries in the lockfile |
| `web/frontend/`: `npm run build` | Passed with TypeScript checking using a real local dependency installation |
| `web/`: `pwsh -NoProfile -File scripts/tests/test-local-db.ps1` | 13 isolated cases passed; no live database used |

Python checks reused the existing matching local interpreters while importing the relocated source. They did not create a production database or new recording jobs. The final frontend install uses its own locked dependencies; a temporary shared dependency junction was rejected by Turbopack and was removed before the successful build. No workaround for that local junction was added to production configuration.

The publication review checks the Git index for private/runtime filenames, new model/video binaries, personal absolute paths and common credential/private-key patterns. It permits only unchanged media/model entries already present in the public upstream history. Private demo footage and stills are absent. Ignore rules do not retroactively remove the public fork's original history.

Historical 2026-09-20 records in the other documents remain historical evidence. This publication did not repeat full video inference, a live AI model call, browser coverage, Docker deployment or model-accuracy evaluation.
