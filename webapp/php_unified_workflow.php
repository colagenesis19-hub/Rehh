<?php

declare(strict_types=1);

/**
 * Unified workflow bridge.
 *
 * The Telegram chatbot already persists replacement workflow fields in `orders`.
 * This module makes that same table the source of truth for Mini App forms too:
 * - Mini App reads chatbot-filled fields before rendering CONFIG/REPORT/STO.
 * - Mini App draft/completion writes are mirrored back into `orders`.
 * - Both interfaces therefore resume the same INET/ticket state.
 */

const UNIFIED_WORKFLOW_FIELDS = [
    'ticket_id', 'service_number', 'voip_number', 'customer_name', 'address',
    'customer_phone', 'old_sn', 'new_sn', 'ont_type', 'sto', 'valins_id',
    'result', 'config_description', 'report_description', 'assigned_technician',
];

function unified_ensure_orders_schema(): void {
    db()->exec("CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id TEXT NOT NULL DEFAULT '',
        service_number TEXT NOT NULL DEFAULT '',
        voip_number TEXT NOT NULL DEFAULT '',
        customer_name TEXT NOT NULL DEFAULT '',
        address TEXT NOT NULL DEFAULT '',
        customer_phone TEXT NOT NULL DEFAULT '',
        old_sn TEXT NOT NULL DEFAULT '',
        new_sn TEXT NOT NULL DEFAULT '',
        ont_type TEXT NOT NULL DEFAULT '',
        sto TEXT NOT NULL DEFAULT '',
        valins_id TEXT NOT NULL DEFAULT '',
        result TEXT NOT NULL DEFAULT '',
        config_description TEXT NOT NULL DEFAULT '',
        report_description TEXT NOT NULL DEFAULT '',
        assigned_technician TEXT NOT NULL DEFAULT '',
        source_file TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_orders_service ON orders(service_number)");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_orders_ticket ON orders(ticket_id)");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_orders_assigned ON orders(assigned_technician)");
}

function unified_normalize_value(string $field, mixed $value): string {
    $value = trim((string)$value);
    if (in_array($field, ['old_sn','new_sn','ont_type','sto'], true)) {
        $value = strtoupper($value);
    }
    return $value;
}

function unified_find_master(string $serviceNumber, string $ticketId=''): ?array {
    unified_ensure_orders_schema();
    $serviceNumber = trim($serviceNumber);
    $ticketId = normalize_ticket($ticketId);

    if ($serviceNumber !== '') {
        $st = db()->prepare("SELECT * FROM orders WHERE TRIM(service_number)=? ORDER BY id DESC LIMIT 1");
        $st->execute([$serviceNumber]);
        $row = $st->fetch();
        if ($row) return $row;
    }
    if ($ticketId !== '') {
        $st = db()->prepare("SELECT * FROM orders WHERE UPPER(TRIM(ticket_id))=? ORDER BY id DESC LIMIT 1");
        $st->execute([strtoupper($ticketId)]);
        $row = $st->fetch();
        if ($row) return $row;
    }
    return null;
}

function unified_history_kinds(int $telegramId, string $serviceNumber): array {
    if ($telegramId <= 0 || $serviceNumber === '' || !table_exists('histories')) return [];
    $st = db()->prepare("SELECT DISTINCT UPPER(kind) kind FROM histories WHERE telegram_id=? AND TRIM(service_number)=? ORDER BY kind");
    $st->execute([$telegramId, $serviceNumber]);
    return array_values(array_filter(array_map(
        static fn(array $row): string => trim((string)($row['kind'] ?? '')),
        $st->fetchAll()
    )));
}

function unified_merge_order_payload(array $payload, int $telegramId=0): array {
    $service = trim((string)($payload['service_number'] ?? ''));
    $ticket = trim((string)($payload['ticket_id'] ?? ''));
    $master = unified_find_master($service, $ticket);
    if (!$master) {
        $payload['unified'] = false;
        $payload['completed_kinds'] = unified_history_kinds($telegramId, $service);
        return $payload;
    }

    // Master workflow fields take precedence when they already contain a value.
    // Sheet-only presentation fields (package, ONU RX, RCA, area, source) stay intact.
    foreach (UNIFIED_WORKFLOW_FIELDS as $field) {
        if (!array_key_exists($field, $master)) continue;
        $value = trim((string)$master[$field]);
        if ($value !== '') $payload[$field] = $value;
    }

    $payload['unified'] = true;
    $payload['unified_updated_at'] = (string)($master['updated_at'] ?? '');
    $payload['completed_kinds'] = unified_history_kinds(
        $telegramId,
        trim((string)($payload['service_number'] ?? $service))
    );
    return $payload;
}

function unified_enrich_open_orders_result(array $result, int $viewerTelegramId): array {
    if (!($result['ok'] ?? false)) return $result;
    foreach (($result['areas'] ?? []) as &$area) {
        foreach (($area['orders'] ?? []) as &$order) {
            $order = unified_merge_order_payload($order, $viewerTelegramId);
        }
        unset($order);
    }
    unset($area);
    $result['workflow_source'] = 'orders';
    $result['unified_workflow'] = true;
    return $result;
}

function unified_payload_data(array $payload): array {
    $order = is_array($payload['order'] ?? null) ? $payload['order'] : [];
    $data = is_array($payload['data'] ?? null) ? $payload['data'] : [];
    // Filled form data wins over the original order payload.
    return array_merge($order, $data, $payload);
}

function unified_sync_workflow_payload(array $payload): array {
    unified_ensure_orders_schema();
    $rawTelegram = trim((string)($payload['telegram_id'] ?? ''));
    if (!ctype_digit($rawTelegram)) {
        return ['ok'=>false,'error'=>'telegram_id_required','message'=>'Telegram ID tidak valid.'];
    }
    $telegramId = (int)$rawTelegram;
    $tech = technician_by_telegram($telegramId);
    if (!$tech) {
        return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    }

    $source = unified_payload_data($payload);
    $service = trim((string)($source['service_number'] ?? $source['internet_number'] ?? ''));
    $ticket = trim((string)($source['ticket_id'] ?? ''));
    if ($service === '' && normalize_ticket($ticket) === '') {
        return ['ok'=>false,'error'=>'identity_required','message'=>'INET atau tiket wajib tersedia.'];
    }

    $values = [];
    foreach (UNIFIED_WORKFLOW_FIELDS as $field) {
        $raw = $field === 'service_number'
            ? ($source['service_number'] ?? $source['internet_number'] ?? '')
            : ($source[$field] ?? '');
        $values[$field] = unified_normalize_value($field, $raw);
    }
    $values['assigned_technician'] = trim((string)($tech['name'] ?? $values['assigned_technician'] ?? ''));

    $existing = unified_find_master($values['service_number'], $values['ticket_id']);
    $now = (new DateTimeImmutable('now'))->format('Y-m-d\TH:i:s\Z');

    if ($existing) {
        $sets=[]; $params=[];
        foreach (UNIFIED_WORKFLOW_FIELDS as $field) {
            if ($values[$field] === '') continue;
            $sets[] = "$field=?";
            $params[] = $values[$field];
        }
        $sets[] = "source_file=?";
        $params[] = 'MINIAPP_UNIFIED';
        $sets[] = "updated_at=?";
        $params[] = $now;
        $params[] = (int)$existing['id'];
        db()->prepare('UPDATE orders SET '.implode(',', $sets).' WHERE id=?')->execute($params);
        $id = (int)$existing['id'];
        $mode = 'updated';
    } else {
        $cols = UNIFIED_WORKFLOW_FIELDS;
        $insertValues = array_map(static fn(string $field): string => $values[$field], $cols);
        $cols[]='source_file'; $insertValues[]='MINIAPP_UNIFIED';
        $cols[]='created_at'; $insertValues[]=$now;
        $cols[]='updated_at'; $insertValues[]=$now;
        $sql='INSERT INTO orders ('.implode(',', $cols).') VALUES ('.implode(',', array_fill(0,count($cols),'?')).')';
        $st=db()->prepare($sql); $st->execute($insertValues);
        $id=(int)db()->lastInsertId();
        $mode='inserted';
    }

    $row = db()->query('SELECT * FROM orders WHERE id='.(int)$id.' LIMIT 1')->fetch() ?: [];
    return [
        'ok'=>true,
        'mode'=>$mode,
        'order'=>$row,
        'completed_kinds'=>unified_history_kinds($telegramId, trim((string)($row['service_number'] ?? $service))),
        'updated_at'=>(string)($row['updated_at'] ?? $now),
    ];
}

function unified_get_workflow_state(int $telegramId, string $serviceNumber='', string $ticketId=''): array {
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $row = unified_find_master($serviceNumber, $ticketId);
    if (!$row) return ['ok'=>true,'found'=>false,'order'=>null,'completed_kinds'=>[]];

    // Prevent a normal technician from querying another technician's workflow by INET.
    $owner = norm_name($row['assigned_technician'] ?? '');
    $viewer = norm_name($tech['name'] ?? '');
    if ($owner !== '' && $viewer !== '' && $owner !== $viewer) {
        return ['ok'=>false,'error'=>'forbidden','message'=>'Workflow ini milik teknisi lain.'];
    }

    $service = trim((string)($row['service_number'] ?? $serviceNumber));
    return [
        'ok'=>true,
        'found'=>true,
        'order'=>$row,
        'completed_kinds'=>unified_history_kinds($telegramId, $service),
    ];
}
