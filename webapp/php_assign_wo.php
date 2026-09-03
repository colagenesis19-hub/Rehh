<?php

declare(strict_types=1);

/**
 * Bidirectional HSA/OSA work-order assignment.
 * Google Sheets remains the order source of truth. Assignment writes the
 * technician name back to the matching INET row, while SQLite keeps a local
 * copy so the workflow can continue immediately.
 */

function assign_wo_b64url(string $value): string {
    return rtrim(strtr(base64_encode($value), '+/', '-_'), '=');
}

function assign_wo_credentials(): array {
    $raw = trim((string)(getenv('GOOGLE_SERVICE_ACCOUNT_JSON') ?: ''));
    if ($raw === '') throw new RuntimeException('GOOGLE_SERVICE_ACCOUNT_JSON belum dikonfigurasi di container.');
    if (is_file($raw)) $raw = (string)file_get_contents($raw);
    $json = json_decode($raw, true);
    if (!is_array($json) || empty($json['client_email']) || empty($json['private_key'])) {
        throw new RuntimeException('GOOGLE_SERVICE_ACCOUNT_JSON tidak valid.');
    }
    return $json;
}

function assign_wo_http(string $url, string $method='GET', ?array $payload=null, array $headers=[]): array {
    $headers = array_merge(['Accept: application/json'], $headers);
    $options = ['http'=>[
        'method'=>$method,
        'timeout'=>25,
        'ignore_errors'=>true,
        'header'=>implode("\r\n", $headers),
    ]];
    if ($payload !== null) {
        $body=json_encode($payload, JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);
        $options['http']['content']=$body;
        $options['http']['header'].="\r\nContent-Type: application/json";
    }
    $ctx=stream_context_create($options);
    $raw=@file_get_contents($url,false,$ctx);
    $status=0;
    foreach (($http_response_header ?? []) as $h) if (preg_match('/^HTTP\/\S+\s+(\d+)/i',$h,$m)) {$status=(int)$m[1];break;}
    $data=json_decode((string)$raw,true);
    if ($status>=400 || $raw===false) {
        $message=is_array($data)?(string)($data['error']['message']??$data['error']??'Google API error'):'Google API error';
        throw new RuntimeException($message.' (HTTP '.$status.')');
    }
    return is_array($data)?$data:[];
}

function assign_wo_access(int $telegramId): ?array {
    $viewer=technician_by_telegram($telegramId);
    if (!$viewer || !technician_privileged_manager($telegramId,$viewer)) return null;
    return $viewer;
}

function assign_wo_access_role(array $viewer): string {
    if (in_array((int)($viewer['telegram_id']??0), technician_admin_ids(), true)) return 'ADMIN';
    if (trim((string)($viewer['nik']??''))==='86240021') return 'HSA';
    return 'OSA';
}

function assign_wo_access_token(): string {
    $cred=assign_wo_credentials();
    $now=time();
    $header=assign_wo_b64url(json_encode(['alg'=>'RS256','typ'=>'JWT'],JSON_UNESCAPED_SLASHES));
    $claims=assign_wo_b64url(json_encode([
        'iss'=>$cred['client_email'],
        'scope'=>'https://www.googleapis.com/auth/spreadsheets',
        'aud'=>'https://oauth2.googleapis.com/token',
        'iat'=>$now,
        'exp'=>$now+3600,
    ],JSON_UNESCAPED_SLASHES));
    $unsigned=$header.'.'.$claims;
    $signature='';
    if (!openssl_sign($unsigned,$signature,$cred['private_key'],OPENSSL_ALGO_SHA256)) throw new RuntimeException('Gagal menandatangani Google JWT.');
    $jwt=$unsigned.'.'.assign_wo_b64url($signature);
    $options=['http'=>['method'=>'POST','timeout'=>20,'ignore_errors'=>true,'header'=>"Content-Type: application/x-www-form-urlencoded\r\n",'content'=>http_build_query(['grant_type'=>'urn:ietf:params:oauth:grant-type:jwt-bearer','assertion'=>$jwt])]];
    $raw=@file_get_contents('https://oauth2.googleapis.com/token',false,stream_context_create($options));
    $data=json_decode((string)$raw,true);
    if (!is_array($data)||empty($data['access_token'])) throw new RuntimeException((string)($data['error_description']??'Gagal mendapatkan token Google.'));
    return (string)$data['access_token'];
}

function assign_wo_sheet_config(): array {
    return get_settings();
}

function assign_wo_sheet_metadata(string $token,string $spreadsheetId,string $gid): array {
    $url='https://sheets.googleapis.com/v4/spreadsheets/'.rawurlencode($spreadsheetId).'?fields=sheets(properties(sheetId,title))';
    $data=assign_wo_http($url,'GET',null,['Authorization: Bearer '.$token]);
    foreach (($data['sheets']??[]) as $sheet) {
        $p=$sheet['properties']??[];
        if ((string)($p['sheetId']??'')===(string)$gid) return ['title'=>(string)($p['title']??'Sheet1'),'sheetId'=>(string)$gid];
    }
    $first=$data['sheets'][0]['properties']??[];
    return ['title'=>(string)($first['title']??'Sheet1'),'sheetId'=>(string)($first['sheetId']??$gid)];
}

function assign_wo_col_letter(int $index): string {
    $s='';$n=$index+1;
    while($n>0){$r=($n-1)%26;$s=chr(65+$r).$s;$n=intdiv($n-1,26);}return $s;
}

function assign_wo_read_sheet(string $token,string $spreadsheetId,string $title): array {
    $range="'".str_replace("'","''",$title)."'!A:ZZ";
    $url='https://sheets.googleapis.com/v4/spreadsheets/'.rawurlencode($spreadsheetId).'/values/'.rawurlencode($range);
    $data=assign_wo_http($url,'GET',null,['Authorization: Bearer '.$token]);
    return is_array($data['values']??null)?$data['values']:[];
}

function assign_wo_find_column(array $headers,array $aliases): ?int {
    $wanted=array_map('norm',$aliases);
    foreach($headers as $i=>$h) if(in_array(norm($h),$wanted,true)) return $i;
    return null;
}

function assign_wo_write_cell(string $token,string $spreadsheetId,string $title,string $range,string $value): void {
    $a1="'".str_replace("'","''",$title)."'!$range";
    $url='https://sheets.googleapis.com/v4/spreadsheets/'.rawurlencode($spreadsheetId).'/values/'.rawurlencode($a1).'?valueInputOption=USER_ENTERED';
    assign_wo_http($url,'PUT',['range'=>$a1,'majorDimension'=>'ROWS','values'=>[[$value]]],['Authorization: Bearer '.$token]);
}

function assign_wo_local_sync(array $order,string $technician): void {
    if (!function_exists('unified_ensure_orders_schema')) return;
    unified_ensure_orders_schema();
    $service=trim((string)($order['service_number']??''));
    $ticket=trim((string)($order['ticket_id']??''));
    if ($service===''&&$ticket==='') return;
    $existing=unified_find_master($service,$ticket);
    $now=(new DateTimeImmutable('now'))->format('Y-m-d\\TH:i:s\\Z');
    if ($existing) {
        db()->prepare('UPDATE orders SET assigned_technician=?, source_file=?, updated_at=? WHERE id=?')->execute([$technician,'HSA_ASSIGNMENT',$now,(int)$existing['id']]);
        return;
    }
    db()->prepare("INSERT INTO orders (ticket_id,service_number,customer_name,address,sto,assigned_technician,source_file,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)")
        ->execute([$ticket,$service,(string)($order['customer_name']??''),(string)($order['address']??''),(string)($order['sto']??'MYR'),$technician,'HSA_ASSIGNMENT',$now,$now]);
}

function assign_wo_list(int $telegramId): array {
    $viewer=assign_wo_access($telegramId);
    if (!$viewer) return ['ok'=>false,'error'=>'forbidden','message'=>'ASSIGN WO hanya dapat digunakan HSA/OSA/admin.'];
    $masters=technician_master_rows();
    $technicians=[];
    foreach($masters as $m){
        $nik=preg_replace('/\\D/','',(string)($m['nik']??''))?:'';
        $role=strtoupper(trim((string)($m['role']??'')));
        // The current website roster is intentionally restricted to HSA only.
        if($nik!=='86240021' && $role!=='HSA') continue;
        $name=trim((string)($m['canonical_name']??''));
        if($name==='') continue;
        $technicians[]=['nik'=>(string)$m['nik'],'name'=>$name,'sto'=>(string)($m['sto']??''),'telegram_id'=>(int)($m['telegram_id']??0)];
    }
    $refs=orderanku_fetch_sheet(true);
    $orders=[];
    foreach($refs as $row){
        if(orderanku_sheet_bucket($row)!=='open') continue;
        $service=trim((string)($row['service_number']??''));
        if($service==='') continue;
        $orders[$service]=array_merge($row,['assigned_technician'=>trim((string)($row['assigned_technician']??''))]);
    }
    $orders=array_values($orders);
    usort($orders,fn($a,$b)=>strnatcasecmp((string)($a['address']??''),(string)($b['address']??'')));
    return ['ok'=>true,'role'=>assign_wo_access_role($viewer),'technicians'=>$technicians,'orders'=>$orders,'source'=>'Google Sheets'];
}

function assign_wo_apply(array $payload): array {
    $telegramId=(int)($payload['telegram_id']??0);
    $viewer=assign_wo_access($telegramId);
    if (!$viewer) return ['ok'=>false,'error'=>'forbidden','message'=>'ASSIGN WO hanya dapat digunakan HSA/OSA/admin.'];
    $targetNik=preg_replace('/\\D/','',(string)($payload['target_nik']??''))?:'';
    $services=array_values(array_unique(array_filter(array_map(static fn($v)=>trim((string)$v),(array)$payload['service_numbers']))));
    if($targetNik===''||!$services) return ['ok'=>false,'error'=>'invalid_request','message'=>'Teknisi dan minimal satu INET wajib dipilih.'];
    $target=null;
    foreach(technician_master_rows() as $m) {
        $nik=preg_replace('/\\D/','',(string)($m['nik']??''))?:'';
        $role=strtoupper(trim((string)($m['role']??'')));
        if($nik===$targetNik && ($nik==='86240021' || $role==='HSA')){$target=$m;break;}
    }
    if(!$target) return ['ok'=>false,'error'=>'technician_not_found','message'=>'Teknisi tujuan tidak ditemukan di Master Teknisi.'];
    $settings=assign_wo_sheet_config();
    $spreadsheetId=(string)$settings['google_sheet_id'];$gid=(string)$settings['google_sheet_gid'];
    $token=assign_wo_access_token();$sheet=assign_wo_sheet_metadata($token,$spreadsheetId,$gid);$rows=assign_wo_read_sheet($token,$spreadsheetId,$sheet['title']);
    if(!$rows) throw new RuntimeException('Google Sheet kosong atau tidak dapat dibaca.');
    $headers=$rows[0]??[];
    $serviceCol=assign_wo_find_column($headers,header_aliases()['service_number']);
    if($serviceCol===null) throw new RuntimeException('Kolom INET/NO SERVICE tidak ditemukan.');
    $techCol=assign_wo_find_column($headers,header_aliases()['assigned_technician']);
    if($techCol===null){
        $techCol=count($headers);assign_wo_write_cell($token,$spreadsheetId,$sheet['title'],assign_wo_col_letter($techCol).'1','NAMA PETUGAS');
    }
    $wanted=array_fill_keys($services,true);$found=[];$skipped=[];
    foreach($rows as $i=>$row){
        if($i===0)continue;
        $service=trim((string)($row[$serviceCol]??''));
        if($service===''||!isset($wanted[$service]))continue;
        $current=trim((string)($row[$techCol]??''));
        if($current!=='' && norm_name($current)!==norm_name((string)$target['canonical_name'])){$skipped[]=['service_number'=>$service,'assigned_technician'=>$current];continue;}
        assign_wo_write_cell($token,$spreadsheetId,$sheet['title'],assign_wo_col_letter($techCol).($i+1),(string)$target['canonical_name']);
        $found[]=$service;
        $order=['service_number'=>$service,'assigned_technician'=>(string)$target['canonical_name']];
        foreach($rows[0] as $j=>$h){$key=norm($h);if($j<count($row)){
            if(in_array($key,['NAMA PELANGGAN','CUSTOMER NAME','NAMA'],true))$order['customer_name']=$row[$j];
            if(in_array($key,['ALAMAT','ADDRESS','ALAMAT PELANGGAN'],true))$order['address']=$row[$j];
            if(in_array($key,['STO','KODE STO'],true))$order['sto']=$row[$j];
            if(in_array($key,['TIKET','TICKET','TICKET ID','TIKET ID','NO TIKET'],true))$order['ticket_id']=$row[$j];
        }}
        assign_wo_local_sync($order,(string)$target['canonical_name']);
    }
    if(!$found) return ['ok'=>false,'error'=>'not_found','message'=>'INET tidak ditemukan sebagai OPEN di Google Sheet atau sudah di-assign ke teknisi lain.','skipped'=>$skipped];
    return ['ok'=>true,'assigned'=>$found,'skipped'=>$skipped,'technician'=>['nik'=>$targetNik,'name'=>$target['canonical_name']],'source'=>'Google Sheets'];
}
