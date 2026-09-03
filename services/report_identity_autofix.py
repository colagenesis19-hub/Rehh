from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from config import settings


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _legacy_name_matches(old_name: str, canonical_name: str, canonical_nik: str) -> bool:
    old = _norm(old_name)
    name = _norm(canonical_name)
    nik = str(canonical_nik or "").strip()
    if not old or not name:
        return False
    return old == name or (nik and old == f"{name} {nik}")


def _repair_explicit_identity(
    conn: sqlite3.Connection,
    canonical_nik: str,
    canonical_name: str,
) -> int:
    rows = conn.execute(
        "SELECT service_number, period_start, technician_nik, technician_name FROM report_group_orders"
    ).fetchall()
    changed = 0
    for service_number, period_start, old_nik, old_name in rows:
        if not _legacy_name_matches(str(old_name or ""), canonical_name, canonical_nik):
            continue
        if str(old_nik or "").strip() == canonical_nik and _norm(str(old_name or "")) == _norm(canonical_name):
            continue
        conn.execute(
            """
            UPDATE report_group_orders
               SET technician_nik = ?, technician_name = ?
             WHERE service_number = ? AND period_start = ?
            """,
            (canonical_nik, canonical_name, str(service_number), str(period_start)),
        )
        changed += 1
    return changed


def _repair_registered_identities(conn: sqlite3.Connection) -> int:
    technicians = conn.execute(
        "SELECT nik, name FROM technicians WHERE TRIM(nik) != '' AND TRIM(name) != ''"
    ).fetchall()
    changed = 0
    # Only auto-merge names that resolve to exactly one registered NIK.
    grouped: dict[str, list[tuple[str, str]]] = {}
    for nik, name in technicians:
        grouped.setdefault(_norm(str(name or "")), []).append((str(nik or "").strip(), str(name or "").strip()))
    for _, identities in grouped.items():
        unique = {(nik, _norm(name)): (nik, name) for nik, name in identities if nik}
        if len(unique) != 1:
            continue
        nik, name = next(iter(unique.values()))
        changed += _repair_explicit_identity(conn, nik, name)
    return changed


def _install_triggers(conn: sqlite3.Connection) -> None:
    # Resolve name-only rows to a canonical registered technician when the name is unique.
    # Also accepts the common malformed form "NAMA TEKNISI 26070177".
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS trg_report_identity_autofix_insert;
        DROP TRIGGER IF EXISTS trg_report_identity_autofix_update;

        CREATE TRIGGER trg_report_identity_autofix_insert
        AFTER INSERT ON report_group_orders
        BEGIN
            UPDATE report_group_orders
               SET technician_nik = COALESCE((
                       SELECT t.nik
                         FROM technicians t
                        WHERE TRIM(t.nik) != ''
                          AND TRIM(t.name) != ''
                          AND (
                               UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name))
                            OR UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                          )
                          AND (
                              UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                              OR (SELECT COUNT(DISTINCT t2.nik)
                                    FROM technicians t2
                                   WHERE UPPER(TRIM(t2.name)) = UPPER(TRIM(t.name))
                                     AND TRIM(t2.nik) != '') = 1
                          )
                        LIMIT 1
                   ), technician_nik),
                   technician_name = COALESCE((
                       SELECT t.name
                         FROM technicians t
                        WHERE TRIM(t.nik) != ''
                          AND TRIM(t.name) != ''
                          AND (
                               UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name))
                            OR UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                          )
                          AND (
                              UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                              OR (SELECT COUNT(DISTINCT t2.nik)
                                    FROM technicians t2
                                   WHERE UPPER(TRIM(t2.name)) = UPPER(TRIM(t.name))
                                     AND TRIM(t2.nik) != '') = 1
                          )
                        LIMIT 1
                   ), technician_name)
             WHERE service_number = NEW.service_number
               AND period_start = NEW.period_start;
        END;

        CREATE TRIGGER trg_report_identity_autofix_update
        AFTER UPDATE OF technician_nik, technician_name ON report_group_orders
        WHEN NEW.technician_nik != OLD.technician_nik OR NEW.technician_name != OLD.technician_name
        BEGIN
            UPDATE report_group_orders
               SET technician_nik = COALESCE((
                       SELECT t.nik
                         FROM technicians t
                        WHERE TRIM(t.nik) != ''
                          AND TRIM(t.name) != ''
                          AND (
                               UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name))
                            OR UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                          )
                          AND (
                              UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                              OR (SELECT COUNT(DISTINCT t2.nik)
                                    FROM technicians t2
                                   WHERE UPPER(TRIM(t2.name)) = UPPER(TRIM(t.name))
                                     AND TRIM(t2.nik) != '') = 1
                          )
                        LIMIT 1
                   ), technician_nik),
                   technician_name = COALESCE((
                       SELECT t.name
                         FROM technicians t
                        WHERE TRIM(t.nik) != ''
                          AND TRIM(t.name) != ''
                          AND (
                               UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name))
                            OR UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                          )
                          AND (
                              UPPER(TRIM(NEW.technician_name)) = UPPER(TRIM(t.name || ' ' || t.nik))
                              OR (SELECT COUNT(DISTINCT t2.nik)
                                    FROM technicians t2
                                   WHERE UPPER(TRIM(t2.name)) = UPPER(TRIM(t.name))
                                     AND TRIM(t2.nik) != '') = 1
                          )
                        LIMIT 1
                   ), technician_name)
             WHERE service_number = NEW.service_number
               AND period_start = NEW.period_start;
        END;
        """
    )


def apply(database_path: Path, nik: str = "", name: str = "") -> tuple[int, int]:
    database_path = Path(database_path)
    with sqlite3.connect(database_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "report_group_orders" not in tables or "technicians" not in tables:
            raise RuntimeError("Tabel report_group_orders/technicians belum tersedia")
        explicit = 0
        if nik.strip() and name.strip():
            explicit = _repair_explicit_identity(conn, nik.strip(), " ".join(name.strip().split()))
        automatic = _repair_registered_identities(conn)
        _install_triggers(conn)
        conn.commit()
    return explicit, automatic


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair dan pasang auto-fix identitas report teknisi")
    parser.add_argument("nik", nargs="?", default="")
    parser.add_argument("name", nargs="?", default="")
    args = parser.parse_args()
    explicit, automatic = apply(settings.database_path, args.nik, args.name)
    print(f"Report identity autofix aktif. explicit={explicit}, registered={automatic}")


if __name__ == "__main__":
    main()
