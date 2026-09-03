<?php

declare(strict_types=1);

require_once __DIR__ . '/php_backend.php';

/**
 * PHP compatibility layer for behavior that was previously spread across
 * server.py + server_ext.py + server_full.py + jagir_ext.py.
 */

function load_rca_summary_php(string $area): array {
    $area = strtoupper(trim($area));
    $merged = [];

    // Business rule: Google Order Sheet is MANYAR/MYR only.
    // Never leak Sheet RCA into JAGIR/JGR.
    if ($area !== 'JGR') {
        try {
            foreach (fetch_sheet(false) as $row) {
                $service = trim((string)($row['service_number'] ?? ''));
                $rca = norm($row['rca'] ?? '');
                if ($service === '' || $rca === '' || in_array($rca, ['-','N/A','NA','NONE','#N/A'], true)) continue;
                $merged[$service] = ['rca'=>$rca, 'source'=>'SHEET', 'sto'=>'MYR'];
            }
        } catch (Throwable $e) {
            error_log('[miniapp-php] sheet RCA unavailable: ' . $e->getMessage());
        }
    }

    if (table_exists('kendala_updates')) {
        try {
            $rows = db()->query(
                "SELECT k.service_number,k.rca FROM kendala_updates k
                 JOIN (SELECT service_number,MAX(id) max_id FROM kendala_updates GROUP BY service_number) x
                   ON x.max_id=k.id ORDER BY k.id DESC"
            )->fetchAll();
            foreach ($rows as $row) {
                $service = trim((string)($row['service_number'] ?? ''));
                $rca = norm($row['rca'] ?? '');
                if ($service === '' || $rca === '' || in_array($rca, ['-','N/A','NA','NONE','#N/A'], true)) continue;

                $sto = '';
                if (table_exists('report_area_orders')) {
                    $st = db()->prepare('SELECT sto_code FROM report_area_orders WHERE service_number=? ORDER BY period_start DESC LIMIT 1');
                    $st->execute([$service]);
                    $sto = strtoupper(trim((string)($st->fetchColumn() ?: '')));
                }
                if ($sto === '' && table_exists('orders')) {
                    $st = db()->prepare('SELECT sto FROM orders WHERE service_number=? ORDER BY id DESC LIMIT 1');
                    $st->execute([$service]);
                    $sto = strtoupper(trim((string)($st->fetchColumn() ?: '')));
                }
                if (in_array($area, ['MYR','JGR'], true) && $sto !== $area) continue;
                $merged[$service] = ['rca'=>$rca, 'source'=>'KENDALA', 'sto'=>$sto];
            }
        } catch (Throwable $e) {
            error_log('[miniapp-php] kendala RCA unavailable: ' . $e->getMessage());
        }
    }

    $counts=[]; $sheet=0; $kendala=0;
    foreach ($merged as $item) {
        $counts[$item['rca']] = ($counts[$item['rca']] ?? 0) + 1;
        if ($item['source'] === 'KENDALA') $kendala++; else $sheet++;
    }
    arsort($counts);
    $total = array_sum($counts);
    $items=[];
    foreach ($counts as $label=>$count) {
        $items[]=['label'=>$label,'count'=>$count,'percent'=>$total ? round($count*100/$total,1) : 0];
    }
    return [
        'total'=>$total,
        'items'=>$items,
        'source'=>'Google Sheet MYR + Grup Kendala',
        'sheet_count'=>$sheet,
        'kendala_count'=>$kendala,
    ];
}

function load_dashboard_php(string $area, string $period): array {
    $payload = load_dashboard($area, $period);
    $payload['rca_summary'] = load_rca_summary_php($area);
    $payload['backend'] = 'php';
    return $payload;
}

function report_raw_day(string $service): string {
    if (!table_exists('report_group_orders')) return '';
    $st = db()->prepare('SELECT substr(MAX(message_date),1,10) FROM report_group_orders WHERE service_number=?');
    $st->execute([$service]);
    return trim((string)($st->fetchColumn() ?: ''));
}

function display_date_id(string $raw): string {
    if ($raw === '') return '-';
    try { return date_label(new DateTimeImmutable(substr($raw,0,10))); }
    catch (Throwable) { return $raw; }
}

function load_my_report_php(int $telegramId): array {
    $tech = technician_by_telegram($telegramId);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];

    $identity = 'NAME:' . norm_name($tech['name'] ?? '');
    $detail = load_technician($identity, 'ALL');
    $byService=[];

    foreach (($detail['orders'] ?? []) as $item) {
        $service = norm_key($item['service_number'] ?? '');
        if ($service === '') continue;
        $row = $item;
        $row['service_number'] = $service;
        $row['raw_day'] = report_raw_day($service);
        $row['date_label'] = display_date_id($row['raw_day']);
        $row['source'] = 'report';
        $byService[$service] = $row;
    }

    ensure_workflow_tables();
    $st = db()->prepare(
        'SELECT service_number,MAX(completed_at) completed_at
         FROM miniapp_completed_workflows WHERE telegram_id=?
         GROUP BY service_number ORDER BY completed_at DESC'
    );
    $st->execute([$telegramId]);
    foreach ($st->fetchAll() as $done) {
        $service = norm_key($done['service_number'] ?? '');
        if ($service === '') continue;
        $completedAt = trim((string)($done['completed_at'] ?? ''));
        $doneDay = substr($completedAt,0,10);

        $hist = db()->prepare(
            'SELECT ticket_id,sto,created_at FROM histories
             WHERE telegram_id=? AND service_number=? ORDER BY id DESC LIMIT 1'
        );
        $hist->execute([$telegramId,$service]);
        $history = $hist->fetch() ?: [];

        $current = $byService[$service] ?? [];
        $currentDay = substr((string)($current['raw_day'] ?? ''),0,10);
        if ($currentDay === '' || ($doneDay !== '' && $doneDay >= $currentDay)) {
            $current['raw_day'] = $doneDay;
            $current['date_label'] = display_date_id($doneDay);
        }
        $current['service_number'] = $service;
        $current['ticket_id'] = trim((string)($current['ticket_id'] ?? $history['ticket_id'] ?? 'MANUAL')) ?: 'MANUAL';
        $current['sto'] = strtoupper(trim((string)($current['sto'] ?? $history['sto'] ?? $tech['sto'] ?? '')));
        $current['area_label'] = trim((string)($current['area_label'] ?? $current['sto'] ?? '-')) ?: '-';
        $current['source'] = isset($byService[$service]) ? 'miniapp+report' : 'miniapp';
        $byService[$service] = $current;
    }

    $orders = array_values($byService);
    usort($orders, fn($a,$b) => strcmp((string)($b['raw_day'] ?? ''),(string)($a['raw_day'] ?? '')) ?: strcmp((string)$a['service_number'],(string)$b['service_number']));

    $today = new DateTimeImmutable('today');
    [$weekStart,$weekEnd] = period_bounds($today);
    $daily=0; $weekly=0;
    foreach ($orders as $order) {
        $day = substr((string)($order['raw_day'] ?? ''),0,10);
        if ($day === $today->format('Y-m-d')) $daily++;
        if ($day !== '' && $day >= $weekStart->format('Y-m-d') && $day <= $weekEnd->format('Y-m-d')) $weekly++;
    }

    $trend=[];
    for ($i=6;$i>=0;$i--) {
        $d=$today->modify("-$i days"); $count=0;
        foreach ($orders as $order) if (substr((string)($order['raw_day'] ?? ''),0,10)===$d->format('Y-m-d')) $count++;
        $trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>$count];
    }

    return [
        'ok'=>true,
        'technician'=>[
            'telegram_id'=>$telegramId,
            'nik'=>(string)($tech['nik'] ?? ''),
            'name'=>(string)($tech['name'] ?? '-'),
            'sto'=>strtoupper(trim((string)($tech['sto'] ?? ''))),
        ],
        'daily'=>$daily,
        'weekly'=>$weekly,
        'all'=>count($orders),
        'orders'=>$orders,
        'trend'=>$trend,
        'backend'=>'php',
    ];
}
