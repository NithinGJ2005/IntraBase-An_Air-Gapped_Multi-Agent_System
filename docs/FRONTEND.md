# Frontend Integration and Accessibility Guide

## Overview

Phase 7 implements the employee chat frontend for the Enterprise Intranet Assistant. The interface provides an accessible, rich React chat experience with document citations, in-flight cancellation, state reset, safe error banners, and restricted administrator diagnostics.

## Architecture

The frontend is implemented in two complementary forms:
1. **Direct FastAPI Static Serving (`app/static/`)**:
   - Zero external build tooling required at runtime.
   - Served directly by FastAPI at `GET /` and `GET /static/...`.
   - Ideal for restricted, offline intranet environments lacking local Node.js installations.
2. **Modular React / TypeScript Source (`frontend/`)**:
   - Complete TypeScript source (`src/App.tsx`, `src/types.ts`, `package.json`, `tsconfig.json`).
   - Prepared for organization CI/CD bundling, Vite development, and enterprise artifact repositories.

## Accessibility and UX Design

- **WCAG 2.1 AA Compliance**:
  - High-contrast custom color palette with HSL dark mode.
  - Visible focus indicators (`:focus-visible`) for keyboard navigation.
  - Semantic HTML landmarks (`<header>`, `<main>`, `<button>`, `<textarea>`).
  - Screen reader announcements via `aria-live="polite"` and `role="log"`.
- **Keyboard Navigation**:
  - `Enter`: Submit inquiry.
  - `Shift + Enter`: Insert multiline break.
  - `Escape`: Cancel query or close open modal dialog.

## Security and Safety Features

- **Safe Citation Display**: Document references expose only safe metadata (`filename`, `document_id`, `page`). No server filesystem paths are exposed to the browser.
- **Graceful Error Handling**:
  - `401 Unauthorized`: Displays authentication configuration banner.
  - `403 Forbidden`: Explains missing server-side permissions (`chat:use`).
  - `429 Too Many Requests`: Informs user of temporary inference queue saturation with retry guidance.
  - `503 Service Unavailable`: Informs user that the local model backend is offline or unready.
- **In-Flight Cancellation**: Employs browser `AbortController` to immediately terminate pending requests.
- **State Reset**: Clears active session messages and in-memory chat state.
- **Restricted Diagnostics**: Accessible only to identities with `admin:diagnostics`, providing visibility into liveness, readiness, audit status, and MCP tool availability.
