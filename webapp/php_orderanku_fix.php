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

function orderanku_fetch_sheet(bool $force=false): array {
    $cache = '/tmp/kerja-bot-orderanku-cache-v5.json';
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
    $raw = @file_get_contents(sheet_csv_url(), false, $ctx);
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
