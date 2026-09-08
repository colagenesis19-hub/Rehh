<?php

declare(strict_types=1);

function injoko_history_date(string $value): string {
    $value = trim($value);
    if ($value === '') return '';
    foreach (['d/m/Y', 'Y-m-d', 'Y-m-d\\TH:i:s'] as $fmt) {
        $dt = DateTimeImmutable::createFromFormat($fmt, $value);
        if ($dt instanceof DateTimeImmutable) return $dt->format('Y-m-d');
    }
    return substr($value, 0, 10);
}

function injoko_history_rows(): array {
    if (!table_exists('injoko_close_reports')) return [];
    try {
        return db()->query(
            "SELECT report_date,technician_nik,technician_name,ticket_id,service_number,old_sn,new_sn,valins_id,result,description,source_message_id,source_message_date
             FROM injoko_close_reports
             WHERE UPPER(TRIM(COALESCE(result,''))) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED')
             ORDER BY id DESC"
        )->fetchAll();
    } catch (Throwable $e) {
        error_log('[miniapp-php] INJOKO history dashboard unavailable: '.$e->getMessage());
        return [];
    }
}

function load_injoko_dashboard_php(string $area, string $period): array {
    $area = strtoupper(trim($area));
    $period = strtolower(trim($period));
    $today = new DateTimeImmutable('today');
    [$weekStart, $weekEnd] = period_bounds($today);
    $rows = injoko_history_rows();
    $items = [];
    foreach ($rows as $row) {
        $date = injoko_history_date((string)($row['report_date'] ?? ''));
        if ($date === '') $date = injoko_history_date((string)($row['source_message_date'] ?? ''));
        $name = trim((string)($row['technician_name'] ?? ''));
        $nik = trim((string)($row['technician_nik'] ?? ''));
        $service = norm_key($row['service_number'] ?? '');
        if ($service === '' || ($name === '' && $nik === '')) continue;
        if ($area !== 'ALL' && $area !== 'IJK') continue;
        $items[] = [
            'date' => $date,
            'nik' => $nik,
            'name' => $name ?: ('NIK '.$nik),
            'service_number' => $service,
            'ticket_id' => normalize_ticket($row['ticket_id'] ?? '') ?: 'MANUAL',
            'sto' => 'IJK',
            'area_label' => 'INJOKO',
            'source' => 'INJOKO CLOSE HISTORY',
        ];
    }

    $filtered = [];
    foreach ($items as $item) {
        $inPeriod = true;
        if ($period === 'daily') $inPeriod = $item['date'] === $today->format('Y-m-d');
        elseif ($period === 'weekly') $inPeriod = $item['date'] >= $weekStart->format('Y-m-d') && $item['date'] <= $weekEnd->format('Y-m-d');
        if ($inPeriod) $filtered[] = $item;
    }

    $grouped = [];
    foreach ($filtered as $item) {
        $key = $item['nik'] !== '' ? 'NIK:'.$item['nik'] : 'NAME:'.norm_name($item['name']);
        if (!isset($grouped[$key])) $grouped[$key] = [
            'key'=>$key,
            'nik'=>$item['nik'],
            'name'=>$item['name'],
            'total'=>0,
            'area_label'=>'INJOKO',
            'sto'=>'IJK',
            'services'=>[],
        ];
        $grouped[$key]['services'][$item['service_number']] = 1;
    }
    $leaderboard = [];
    foreach ($grouped as $g) {
        $g['total'] = count($g['services']);
        unset($g['services']);
        $leaderboard[] = $g;
    }
    usort($leaderboard, fn($a,$b) => $b['total'] <=> $a['total'] ?: strcmp(norm_name($a['name']), norm_name($b['name'])));

    $total = array_sum(array_column($leaderboard, 'total'));
    $active = count($leaderboard);
    $trend = [];
    for ($i=6; $i>=0; $i--) {
        $d = $today->modify("-$i days")->format('Y-m-d');
        $services = [];
        foreach ($items as $item) if ($item['date'] === $d) $services[$item['service_number']] = 1;
        $trend[] = [
            'date'=>$d,
            'label'=>DAYS_ID[((int)(new DateTimeImmutable($d))->format('N'))-1],
            'total'=>count($services),
        ];
    }

    $label = 'Keseluruhan';
    if ($period === 'daily') $label = date_label($today);
    elseif ($period === 'weekly') $label = date_label($weekStart).' - '.date_label($weekEnd);

    return [
        'area'=>'IJK',
        'period'=>$period ?: 'daily',
        'period_label'=>$label,
        'summary'=>[
            'total_close'=>$total,
            'active_technicians'=>$active,
            'average_close'=>$active ? round($total/$active,1) : 0,
        ],
        'trend'=>$trend,
        'leaderboard'=>$leaderboard,
        'rca_summary'=>['total'=>0,'items'=>[],'source'=>'INJOKO CLOSE HISTORY'],
        'backend'=>'php',
        'source'=>'INJOKO CLOSE HISTORY',
    ];
}

function load_injoko_technician_detail_php(string $identity, string $area): array {
    $identity = trim($identity);
    $area = strtoupper(trim($area));
    if ($area !== 'ALL' && $area !== 'IJK') return technician_detail_readonly($identity, $area);
    $rows = injoko_history_rows();
    $targetNik = '';
    $targetName = '';
    if (str_starts_with(strtoupper($identity), 'NIK:')) $targetNik = preg_replace('/\\D/','',substr($identity,4)) ?: '';
    elseif (str_starts_with(strtoupper($identity), 'NAME:')) $targetName = norm_name(substr($identity,5));
    else {
        $targetNik = preg_replace('/\\D/','',$identity) ?: '';
        if ($targetNik === '') $targetName = norm_name($identity);
    }
    $services = [];
    $name = '';
    $nik = $targetNik;
    foreach ($rows as $row) {
        $rNik = preg_replace('/\\D/','',(string)($row['technician_nik'] ?? '')) ?: '';
        $rName = norm_name($row['technician_name'] ?? '');
        if (($targetNik !== '' && $rNik !== $targetNik) || ($targetNik === '' && $targetName !== '' && $rName !== $targetName)) continue;
        $service = norm_key($row['service_number'] ?? '');
        if ($service === '') continue;
        $name = trim((string)($row['technician_name'] ?? '')) ?: $name;
        $nik = $rNik ?: $nik;
        $date = injoko_history_date((string)($row['report_date'] ?? '')) ?: injoko_history_date((string)($row['source_message_date'] ?? ''));
        $services[$service] = [
            'service_number'=>$service,
            'ticket_id'=>normalize_ticket($row['ticket_id'] ?? '') ?: 'MANUAL',
            'area_label'=>'INJOKO',
            'sto'=>'IJK',
            'date_label'=>$date !== '' ? date_label(new DateTimeImmutable($date)) : '-',
            'raw_day'=>$date,
        ];
    }
    $orders = array_values($services);
    usort($orders, fn($a,$b)=>strcmp($b['raw_day'],$a['raw_day']));
    $today = new DateTimeImmutable('today');
    [$ws,$we] = period_bounds($today);
    $daily=0; $weekly=0;
    foreach ($orders as $o) {
        if ($o['raw_day'] === $today->format('Y-m-d')) $daily++;
        if ($o['raw_day'] >= $ws->format('Y-m-d') && $o['raw_day'] <= $we->format('Y-m-d')) $weekly++;
    }
    $trend=[];
    for ($i=6;$i>=0;$i--) {
        $d=$today->modify("-$i days")->format('Y-m-d'); $n=0;
        foreach ($orders as $o) if ($o['raw_day']===$d) $n++;
        $trend[]=['date'=>$d,'label'=>DAYS_ID[((int)(new DateTimeImmutable($d))->format('N'))-1],'total'=>$n];
    }
    foreach ($orders as &$o) unset($o['raw_day']);
    unset($o);
    return [
        'key'=>$nik!==''?'NIK:'.$nik:$identity,
        'nik'=>$nik,
        'name'=>$name ?: '-',
        'daily'=>$daily,
        'weekly'=>$weekly,
        'all'=>count($orders),
        'orders'=>array_slice($orders,0,100),
        'trend'=>$trend,
        'source'=>'INJOKO CLOSE HISTORY',
    ];
}
