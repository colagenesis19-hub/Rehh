<?php

declare(strict_types=1);

function ensure_manja_table(): void {
    db()->exec("CREATE TABLE IF NOT EXISTS miniapp_manja (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        technician_nik TEXT NOT NULL DEFAULT '',
        technician_name TEXT NOT NULL DEFAULT '',
        service_number TEXT NOT NULL,
        appointment_date TEXT NOT NULL DEFAULT '',
        appointment_time TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        source TEXT NOT NULL DEFAULT 'MINI APP',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(telegram_id, service_number)
    )");
}

function manja_ts(string $value): int {
    $ts = strtotime(trim($value));
    return $ts === false ? 0 : $ts;
}

function manja_source_candidate(array $row, string $source): array {
    $status = strtoupper(trim((string)($row['status'] ?? '')));
    $rca = strtoupper(trim((string)($row['rca'] ?? '')));
    $isActive = $source === 'MINI APP'
        ? in_array($status, ['ACTIVE','OPEN','MANJA'], true)
        : ($rca === 'MANJA' && !in_array($status, ['CLOSE','CLOSED','DONE','SELESAI','COMPLETED'], true));
    return [
        'service_number' => trim((string)($row['service_number'] ?? '')),
        'status' => $isActive ? 'ACTIVE' : 'INACTIVE',
        'source' => $source,
        'note' => trim((string)($row['note'] ?? $row['description'] ?? '')),
        'appointment_date' => trim((string)($row['appointment_date'] ?? '')),
        'appointment_time' => trim((string)($row['appointment_time'] ?? '')),
        'updated_at' => trim((string)($row['updated_at'] ?? $row['created_at'] ?? '')),
    ];
}

function load_manja_for_technician(int $telegramId): array {
    ensure_manja_table();
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];

    $latest = [];
    if (table_exists('kendala_updates')) {
        $st = db()->prepare("SELECT k.* FROM kendala_updates k JOIN (
            SELECT service_number, MAX(id) max_id FROM kendala_updates WHERE telegram_id=? GROUP BY service_number
        ) x ON x.max_id=k.id");
        $st->execute([$telegramId]);
        foreach ($st->fetchAll() as $row) {
            $candidate = manja_source_candidate($row, 'WORK ORDER MANYAR /update');
            $service = $candidate['service_number'];
            if ($service !== '') $latest[$service] = $candidate;
        }
    }

    $st = db()->prepare('SELECT * FROM miniapp_manja WHERE telegram_id=?');
    $st->execute([$telegramId]);
    foreach ($st->fetchAll() as $row) {
        $candidate = manja_source_candidate($row, 'MINI APP');
        $service = $candidate['service_number'];
        if ($service === '') continue;
        if (!isset($latest[$service]) || manja_ts($candidate['updated_at']) >= manja_ts($latest[$service]['updated_at'])) {
            $latest[$service] = $candidate;
        }
    }

    $items = [];
    foreach ($latest as $candidate) {
        if ($candidate['status'] !== 'ACTIVE') continue;
        $appointmentAt = '';
        if ($candidate['appointment_date'] !== '') {
            $appointmentAt = $candidate['appointment_date'] . ($candidate['appointment_time'] !== '' ? 'T'.$candidate['appointment_time'] : '');
        }
        $candidate['appointment_at'] = $appointmentAt;
        $items[] = $candidate;
    }
    usort($items, function(array $a, array $b): int {
        $aa = $a['appointment_at'] ?: '9999-12-31T23:59';
        $bb = $b['appointment_at'] ?: '9999-12-31T23:59';
        return strcmp($aa, $bb) ?: strcmp($a['service_number'], $b['service_number']);
    });

    return [
        'ok'=>true,
        'technician'=>['telegram_id'=>$telegramId,'nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto']],
        'count'=>count($items),
        'items'=>$items,
        'sources'=>['WORK ORDER MANYAR /update','MINI APP'],
    ];
}

function save_manja_from_miniapp(array $payload): array {
    ensure_manja_table();
    $raw = trim((string)($payload['telegram_id'] ?? ''));
    $service = preg_replace('/\D/', '', (string)($payload['service_number'] ?? '')) ?: '';
    if (!ctype_digit($raw) || strlen($service) < 6) return ['ok'=>false,'error'=>'invalid_request','message'=>'Telegram ID / INET tidak valid.'];
    $telegramId = (int)$raw;
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar.'];

    $status = strtoupper(trim((string)($payload['status'] ?? 'ACTIVE')));
    if (!in_array($status, ['ACTIVE','CANCELLED','DONE'], true)) $status = 'ACTIVE';
    $date = trim((string)($payload['appointment_date'] ?? ''));
    $time = trim((string)($payload['appointment_time'] ?? ''));
    if ($date !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) return ['ok'=>false,'error'=>'invalid_date','message'=>'Tanggal janji tidak valid.'];
    if ($time !== '' && !preg_match('/^\d{2}:\d{2}$/', $time)) return ['ok'=>false,'error'=>'invalid_time','message'=>'Jam janji tidak valid.'];
    $note = trim((string)($payload['note'] ?? ''));
    $now = (new DateTimeImmutable('now'))->format(DateTimeInterface::ATOM);

    $st = db()->prepare("INSERT INTO miniapp_manja (
        telegram_id,technician_nik,technician_name,service_number,appointment_date,appointment_time,note,status,source,created_at,updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(telegram_id,service_number) DO UPDATE SET
        technician_nik=excluded.technician_nik,
        technician_name=excluded.technician_name,
        appointment_date=excluded.appointment_date,
        appointment_time=excluded.appointment_time,
        note=excluded.note,
        status=excluded.status,
        source='MINI APP',
        updated_at=excluded.updated_at");
    $st->execute([$telegramId,(string)$tech['nik'],(string)$tech['name'],$service,$date,$time,$note,$status,'MINI APP',$now,$now]);

    return ['ok'=>true,'service_number'=>$service,'status'=>$status,'source'=>'MINI APP','updated_at'=>$now];
}
