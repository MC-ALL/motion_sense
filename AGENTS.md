# Repository Guidelines

## Project Structure & Module Organization
This repository is currently documentation-first. All content lives under `docs/`:
- `docs/00-系统总览.md`: system architecture and cross-module topology.
- `docs/01-06-*.md`: subsystem specs (wristband, equipment, environment, gateway, backend, web).
- `docs/07-通讯接口定义.md`: source of truth for BLE/MQTT/REST/WebSocket contracts.
- `docs/08-开发排期.md`: delivery plan, milestones, and test targets.

When adding new docs, keep numeric prefixes (`09-*.md`, `10-*.md`) to preserve reading order.

## Build, Test, and Development Commands
There is no runnable app in this repository yet; contribution work is doc validation and interface consistency.

- `rg --files docs`: list tracked documentation files.
- `rg -n "TODO|FIXME|待补充" docs`: find unresolved items.
- `rg -n "gym/\\+|/api/v1|UUID|topic" docs/07-通讯接口定义.md`: verify interface definitions before editing subsystem docs.
- `npx markdownlint-cli docs/**/*.md` (if available): check Markdown style.

If implementation repos are introduced later, align runtime commands with specs in `docs/04-06`.

## Coding Style & Naming Conventions
- Use clear, concise technical language; keep headings and tables consistent with existing docs.
- Keep protocol fields in `snake_case` (e.g., `heart_rate`, `current_equipment_id`).
- Keep API paths and MQTT topics exactly as specified in `docs/07-通讯接口定义.md`.
- Prefer fenced code blocks with language tags (`yaml`, `sql`, `json`, `bash`).

## Testing Guidelines
- Treat interface consistency as the primary test: any contract change in subsystem docs must be synchronized in `docs/07-通讯接口定义.md`.
- Verify examples remain executable or syntactically valid (SQL, YAML, JSON).
- Preserve performance/quality targets documented in `docs/08-开发排期.md` (for example backend unit-test coverage target `>= 70%`, Playwright E2E flow coverage).

## Commit & Pull Request Guidelines
Git history is not present in this workspace, so no project-specific commit pattern can be inferred. Use:
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`), scoped when useful (e.g., `docs(api): ...`).

PRs should include:
- What changed and why.
- Affected files (for example `docs/07-通讯接口定义.md` and dependent subsystem docs).
- Backward-compatibility impact (topic/path/payload changes).
- Screenshots only when updating UI mockups/diagrams.
