from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_area_tracking_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_area_orders (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            sto_code TEXT NOT NULL,
            area_label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (service_number, period_start)
        )
        """
    )


def record_area_order(
    database_path: Path,
    service_number: str,
    period_start: str,
    sto_code: str,
    area_label: str = "",
) -> None:
    with sqlite3.connect(database_path) as conn:
        ensure_area_tracking_table(conn)
        conn.execute(
            """
            INSERT INTO report_area_orders (
                service_number, period_start, sto_code, area_label
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(service_number, period_start) DO UPDATE SET
                sto_code = excluded.sto_code,
                area_label = excluded.area_label
            """,
            (
                service_number.strip(),
                period_start.strip(),
                sto_code.strip().upper(),
                area_label.strip().upper(),
            ),
        )


def area_order_matches_sql(report_alias: str = "r") -> str:
    """Legacy predicate: direct report-area mapping first, orders STO as fallback."""
    return f"""
    (
        EXISTS (
            SELECT 1 FROM report_area_orders ra
            WHERE ra.service_number = {report_alias}.service_number
              AND ra.period_start = {report_alias}.period_start
              AND UPPER(TRIM(ra.sto_code)) = ?
        )
        OR (
            NOT EXISTS (
                SELECT 1 FROM report_area_orders ra0
                WHERE ra0.service_number = {report_alias}.service_number
                  AND ra0.period_start = {report_alias}.period_start
            )
            AND EXISTS (
                SELECT 1 FROM orders o
                WHERE o.service_number = {report_alias}.service_number
                  AND UPPER(TRIM(o.sto)) = ?
            )
        )
    )
    """


def area_order_condition(
    sto_code: str,
    report_alias: str = "r",
) -> tuple[str, tuple[str, ...]]:
    """Return SQL + params for an area.

    JGR/JAGIR is intentionally 100% internal because it has no Sheet/Excel source.
    Only report_area_orders (created from /sto or Telegram-history import) can classify
    a report as JAGIR. MYR keeps the legacy Sheet fallback for older Manyar records.
    """
    sto = sto_code.strip().upper()
    if sto == "JGR":
        return (
            f"""
            EXISTS (
                SELECT 1 FROM report_area_orders ra
                WHERE ra.service_number = {report_alias}.service_number
                  AND ra.period_start = {report_alias}.period_start
                  AND UPPER(TRIM(ra.sto_code)) = ?
            )
            """,
            (sto,),
        )
    return area_order_matches_sql(report_alias), (sto, sto)
