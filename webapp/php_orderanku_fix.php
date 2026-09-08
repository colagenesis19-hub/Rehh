<?php

declare(strict_types=1);

function orderanku_sheet_bucket(array $row): string {
    $status = norm($row['status'] ?? '');

    if (
        in_array($status, CLOSED_STATUSES, true)
        || str_contains($status, 'CLOSE')
        || str_contains($status, 'CLOSED')
        || str_contains($status, 'DONE')
        || str_contains($status, 'SELESAI')
        || str_contains($status, 'COMPLET')
    ) return 'close';

    if (
        in_array($status, UPDATE_STATUSES, true)
        || str_contains($status, 'UPDATE')
        || str_contains($status, 'PROGRESS')
        || str_contains($status, 'PENDING')
    ) return 'update';

    return 'open';
}

function orderanku_find_header(array $row, array $aliases): ?int {
    $wanted = array_map('norm', $aliases);
    foreach ($row as $index => $header) {
        if (in_array(norm($header), $wanted, true)) return $index;
    }
    return null;
}

const INJOKO_SPREADSHEET_ID = '12FtnVT0yM-YWkwHVCCq8rVxq1hS3PVJDzYmAx-kNNs4';
const INJOKO_SHEET_GID = '0';

function orderanku_injoko_csv_url(): string {
    return 'https://docs.google.com/spreadsheets/d/' . INJOKO_SPREADSHEET_ID . '/export?format=csv&gid=' . INJOKO_SHEET_GID;
}

function orderanku_fetch_sheet(bool $force=false, ?string $csvUrl=null, ?string $cacheKey=null): array {
    $cache = '/tmp/kerja-bot-orderanku-cache-' . ($cacheKey ?: 'default') . '.json';
    if (!$force && is_file($cache) && time() - filemtime($cache) < 30) {
        $decoded = json_decode((string)file_get_contents($cache), true);
        if (is_array($decoded)) return $decoded;
    }

    $ctx = stream_context_create([
        'http' => [
            'timeout' => 20,
            'header' => "User-Agent: INJOKO-Orderanku/1.0\r\n",
        ],
    ]);
    $raw = @file_get_contents($csvUrl ?: sheet_csv_url(), false, $ctx);
    if ($raw === false || trim($raw) === '') throw new RuntimeException('Google Sheets INJOKO tidak dapat dibaca.');

    $fp = fopen('php://temp', 'r+');
    fwrite($fp, preg_replace('/^\xEF\xBB\xBF/', '', $raw));
    rewind($fp);
    $rows = [];
    while (($row = fgetcsv($fp)) !== false) $rows[] = $row;
    fclose($fp);

    $aliases = header_aliases();
    $headerIndex = -1;
    $cols = [];
    foreach (array_slice($rows, 0, 20, true) as $i => $row) {
        $candidate = [];
        foreach ($aliases as $key => $opts) $candidate[$key] = orderanku_find_header($row, $opts);
        $candidate['status_tacpro'] = orderanku_find_header($row, ['STATUS TACPRO', 'STATUS TACTICAL', 'TACTICAL STATUS']);
        $candidate['status_insera'] = orderanku_find_header($row, ['STATUS INSERA TODAY', 'STATUS INSERA', 'INSERA STATUS']);
        if ($candidate['service_number'] !== null && ($candidate['status'] !== null || $candidate['status_tacpro'] !== null || $candidate['status_insera'] !== null)) {
            $headerIndex = $i;
            $cols = $candidate;
            break;
        }
    }
    if ($headerIndex < 0) throw new RuntimeException('Kolom INET/status tidak ditemukan di Google Sheet INJOKO.');

    $out = [];
    for ($i = $headerIndex + 1; $i < count($rows); $i++) {
        $row = $rows[$i];
        $v = [];
        foreach ($cols as $key => $col) $v[$key] = ($col !== null && array_key_exists($col, $row)) ? trim((string)$row[$col]) : '';

        $service = trim($v['service_number']);
        $primaryTicket = normalize_ticket($v['ticket']);
        $inseraTicket = normalize_ticket($v['insera_ticket']);
        $ticket = $inseraTicket ?: $primaryTicket;
        if ($service === '' && $ticket === '') continue;

        $manualStatus = norm($v['status'] ?? '');
        $tacproStatus = norm($v['status_tacpro'] ?? '');
        $inseraStatus = norm($v['status_insera'] ?? '');
        $effectiveStatus = $manualStatus ?: ($tacproStatus ?: $inseraStatus);

        $item = [
            'status' => $effectiveStatus,
            'status_manual' => $manualStatus,
            'status_tacpro' => $tacproStatus,
            'status_insera' => $inseraStatus,
            'ticket_id' => $ticket,
            'service_number' => $service,
            'voip_number' => $v['voip_number'],
            'customer_name' => $v['customer_name'],
            'address' => $v['address'],
            'customer_phone' => $v['customer_phone'],
            'package' => $v['package'],
            'onu_rx' => $v['onu_rx'],
            'rca' => $v['rca'],
            'old_sn' => norm($v['old_sn']),
            'new_sn' => norm($v['new_sn']),
            'ont_type' => norm($v['ont_type']),
            'sto' => norm($v['sto']),
            'valins_id' => $v['valins_id'],
            'config_description' => $v['config_description'],
            'report_description' => $v['report_description'],
            'assigned_technician' => $v['assigned_technician'],
        ];

        $ticketKey = norm_key($ticket);
        $serviceKey = norm_key($service);
        if ($ticketKey === '' && $serviceKey === '') continue;
        $out[$ticketKey . '|' . $serviceKey] = $item;
    }

    @file_put_contents($cache, json_encode($out, JSON_UNESCAPED_UNICODE));
    return $out;
}

function orderanku_injoko_close_matches(): array {
    static $loaded = false;
    static $byService = [];
    static $byTicket = [];
    if ($loaded) return [$byService, $byTicket];
    $loaded = true;
    try {
        if (!table_exists('injoko_close_reports')) return [$byService, $byTicket];
        $rows = db()->query("SELECT service_number, ticket_id, result, report_date, technician_nik, technician_name, old_sn, new_sn, valins_id, description FROM injoko_close_reports WHERE UPPER(TRIM(result)) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED') ORDER BY id DESC")->fetchAll();
        foreach ($rows as $r) {
            $service = preg_replace('/\D+/', '', (string)($r['service_number'] ?? '')) ?: '';
            $ticket = norm_key($r['ticket_id'] ?? '');
            if ($service !== '' && !isset($byService[$service])) $byService[$service] = $r;
            if ($ticket !== '' && !isset($byTicket[$ticket])) $byTicket[$ticket] = $r;
        }
    } catch (Throwable) {}
    return [$byService, $byTicket];
}

function orderanku_apply_injoko_close_history(array $rows): array {
    [$byService, $byTicket] = orderanku_injoko_close_matches();
    if (!$byService && !$byTicket) return $rows;
    foreach ($rows as $key => &$row) {
        $service = preg_replace('/\D+/', '', (string)($row['service_number'] ?? '')) ?: '';
        $ticket = norm_key($row['ticket_id'] ?? '');
        $match = ($service !== '' && isset($byService[$service])) ? $byService[$service] : (($ticket !== '' && isset($byTicket[$ticket])) ? $byTicket[$ticket] : null);
        if (!$match) continue;
        $row['status'] = 'CLOSE';
        $row['status_manual'] = 'CLOSE';
        $row['status_injoko_history'] = 'CLOSE';
        $row['close_report_date'] = (string)($match['report_date'] ?? '');
        $row['close_technician_nik'] = (string)($match['technician_nik'] ?? '');
        $row['close_technician_name'] = (string)($match['technician_name'] ?? '');
        $row['close_old_sn'] = (string)($match['old_sn'] ?? '');
        $row['close_new_sn'] = (string)($match['new_sn'] ?? '');
        $row['close_valins_id'] = (string)($match['valins_id'] ?? '');
        $row['close_description'] = (string)($match['description'] ?? '');
    }
    unset($row);
    return $rows;
}

function orderanku_fetch_injoko_sheet(bool $force=false): array {
    // INJOKO has its own WO spreadsheet. This must not fall back to the
    // MYR/default sheet or to bot_settings.
    $rows = orderanku_fetch_sheet($force, orderanku_injoko_csv_url(), 'injoko-ijk-v1');
    return orderanku_apply_injoko_close_history($rows);
}

function load_my_open_orders_fixed(int $telegramId, bool $force=false): array {
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];

    $refs = orderanku_fetch_sheet($force);
    $wanted = norm_name($tech['name'] ?? '');
    $summary = ['open'=>0,'close'=>0,'update'=>0];
    $orders = [];

    foreach ($refs as $row) {
        if (norm_name($row['assigned_technician'] ?? '') !== $wanted) continue;
        $bucket = orderanku_sheet_bucket($row);
        $summary[$bucket]++;
        if ($bucket === 'open') {
            $orders[] = order_payload($row);
            $orders[array_key_last($orders)]['area'] = 'INJOKO';
            $orders[array_key_last($orders)]['source'] = 'INJOKO';
        }
    }

    usort($orders, fn($a,$b) => strnatcasecmp((string)($a['address']??''), (string)($b['address']??'')));
    $area = [
        'area' => 'INJOKO',
        'open' => count($orders),
        'close' => (int)$summary['close'],
        'update' => (int)$summary['update'],
        'orders' => $orders,
    ];

    return [
        'ok' => true,
        'technician' => [
            'telegram_id' => $telegramId,
            'nik' => $tech['nik'],
            'name' => $tech['name'],
            'sto' => $tech['sto'],
        ],
        'source' => 'INJOKO • GOOGLE SHEET',
        'total_open' => count($orders),
        'total_close' => (int)$summary['close'],
        'total_update' => (int)$summary['update'],
        'total_count' => count($orders) + (int)$summary['close'] + (int)$summary['update'],
        'active_areas' => $orders || $summary['close'] || $summary['update'] ? 1 : 0,
        'areas' => ($orders || $summary['close'] || $summary['update']) ? [$area] : [],
    ];
}
