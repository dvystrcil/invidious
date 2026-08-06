# invidious

Self-hosted [Invidious](https://github.com/iv-org/invidious) — a privacy-friendly YouTube frontend — configured with YouTube's algorithmic recommendation surfaces disabled (`related_videos`, `popular_enabled`, `feed_menu`, `default_home`) while search stays intact.

**Goal** (tracked in [dvystrcil/homelab#848](https://github.com/dvystrcil/homelab/issues/848)): let search-driven video access work normally, without an algorithmic recommendation engine pushing content.

## Layout

- `base/` — namespace, Postgres (Crunchy PGO `PostgresCluster`), the `invidious` and `invidious-companion` Deployments/Services, VPAs, and the Infisical-sourced secrets.
- `overlays/` — the ArgoCD sync target (`kubectl kustomize overlays/`).

## Notes

- Companion (`invidious-companion`) is mandatory upstream, not optional — it replaces `inv-sig-helper`/`youtube-trusted-session-generator` and handles YouTube rate-limiting/token rotation.
- Config is set entirely via `INVIDIOUS_<FIELD>` env vars (verified directly against `src/invidious/config.cr` — every top-level `Config` field is independently overridable), not the `INVIDIOUS_CONFIG` YAML blob.
- Postgres schema is upstream's real `config/sql/*.sql`, concatenated in dependency order, with `GRANT ... TO current_user` adapted to the real app user explicitly (PGO's `databaseInitSQL` runs as the bootstrap connection, not the app's own role).
- No external routing wired yet — access via `kubectl port-forward -n invidious svc/invidious 3000:3000` until the `gateway-services` HTTPRoute is added as a follow-up.
