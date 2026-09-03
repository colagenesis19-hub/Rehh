<?php

declare(strict_types=1);

/**
 * Best-effort technician-master bootstrap.
 *
 * Master/legacy normalization must never make core Mini App endpoints fail.
 * Schema/bootstrap errors are logged and the caller continues using the
 * existing dashboard/report identity logic.
 */
function technician_master_bootstrap(): void {
    try {
        ensure_technician_master_schema();
        db()->exec("CREATE TABLE IF NOT EXISTS technician_master_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)");
        $version='technician-normalization-v2-fail-open';
        $st=db()->prepare('SELECT value FROM technician_master_meta WHERE key=? LIMIT 1');
        $st->execute(['normalization_version']);
        if((string)($st->fetchColumn()?:'')===$version)return;

        try {
            $result=normalize_technician_data();
            db()->prepare("INSERT INTO technician_master_meta(key,value,updated_at) VALUES('normalization_version',?,datetime('now')) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at")->execute([$version]);
            error_log('[miniapp-php] technician master normalized '.(int)($result['total_changed']??0).' rows');
        } catch (Throwable $e) {
            // Legacy tables can have different schemas across deployments.
            // Do not take down Dashboard/Laporan because one migration failed.
            error_log('[miniapp-php] technician master normalization skipped: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
        }
    } catch (Throwable $e) {
        error_log('[miniapp-php] technician master bootstrap skipped: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
    }
}
