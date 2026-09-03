# Upgrade / Deploy notes for INJOKO role & UI rework

This branch implements:
- Add `role` column to `technicians` (default TECHNICIAN) and sets NIK 86240021 -> HSA.
- New API endpoint: `api/areas_status.php` that attempts to compute success percentage per area from existing tables (areas, orders, reports) or falls back to the `area_status` table.
- New API endpoint: `api/me.php` to return currently logged-in user and role (session based).
- Middleware helper: `src/lib/role_check.php` to gate routes by role.
- Frontend helpers: `web/static/js/percentColor.js`, `web/static/js/menu_render.js`.
- Demo template: `web/templates/area_status.html` (uses SVG placeholders and the uploaded KML as assets/SEKTOR INJOKO.kml).

Before merging to main, run these steps on the VPS / production environment:

1. Backup database.
2. Apply migrations:
   mysql -u <user> -p <database> < migrations/20260903_add_role_to_technicians.sql
   mysql -u <user> -p <database> < migrations/20260903_create_area_status.sql

3. Ensure DB connection path used by the new PHP files matches your repo (they expect `src/lib/db.php` to provide a $db PDO instance).

4. Wire `api/me.php` into your authentication/session flow so that `$_SESSION['user_id']` is set after login.

5. Optional: convert KML (assets/SEKTOR INJOKO.kml) into SVG polygons for `web/templates/area_status.html`; tools: `ogr2ogr`, QGIS, or online converters.

6. Rebuild Docker / restart services:
   docker compose build
   docker compose up -d

7. Test endpoints:
   curl http://localhost/api/areas_status.php
   curl http://localhost/api/me.php

Notes:
- The computed query in `api/areas_status.php` expects tables named `areas`, `orders`, and `reports` with columns (`area_id`, `order_id`, `status`) respectively. If your schema differs, edit the SQL accordingly.
- Frontend `menu_render.js` replaces branding strings and controls Input menu per role. It assumes elements contain selectors like `.app-brand`, `#app-title`, `[data-nav]` and `#input-menu`. Adjust selectors to your actual templates.
