<?php

declare(strict_types=1);

const REPORT_SUPERVISOR_NIKS = ['91260038', '94250015'];

function report_is_supervisor(array $tech): bool {
    return in_array(trim((string)($tech['nik'] ?? '')), REPORT_SUPERVISOR_NIKS, true);
}

function report_canonical_technician(array $row): array {
    if (!function_exists('technician_master_resolve')) return $row;
    try {
        $master=technician_master_resolve((string)($row['nik']??''),(string)($row['name']??''));
    } catch (Throwable $e) {
        error_log('[miniapp-php] technician master resolve fallback: '.$e->getMessage());
        return $row;
    }
    if(!$master)return$row;
    $row['nik']=$master['nik'];$row['name']=$master['canonical_name'];
    if(trim((string)($master['sto']??''))!=='')$row['sto']=$master['sto'];
    if(!empty($master['telegram_id']))$row['telegram_id']=(int)$master['telegram_id'];
    return$row;
}

function report_filter_technicians(): array {
    if (!table_exists('technicians')) return [];
    $rows = db()->query("SELECT telegram_id,nik,name,sto FROM technicians WHERE TRIM(COALESCE(nik,''))<>'' AND TRIM(COALESCE(name,''))<>'' ORDER BY name,nik")->fetchAll();
    $out=[];$seen=[];
    foreach ($rows as $row) {
        $row=report_canonical_technician($row);$nik=trim((string)($row['nik']??''));
        if ($nik===''||isset($seen[$nik])) continue;$seen[$nik]=1;
        $out[]=['telegram_id'=>(int)($row['telegram_id']??0),'nik'=>$nik,'name'=>trim((string)($row['name']??'-')) ?: '-','sto'=>strtoupper(trim((string)($row['sto']??'')))];
    }
    usort($out,fn($a,$b)=>strcmp((string)$a['name'],(string)$b['name']) ?: strcmp((string)$a['nik'],(string)$b['nik']));
    return $out;
}

function report_target_by_nik(string $nik): ?array {
    $st=db()->prepare("SELECT id,telegram_id,nik,name,sto FROM technicians WHERE TRIM(nik)=? LIMIT 1");
    $st->execute([trim($nik)]);$row=$st->fetch();
    return $row?report_canonical_technician($row):null;
}

function report_week_counts(array $orders): array {
    $today=new DateTimeImmutable('today');[$weekStart,$weekEnd]=period_bounds($today);$daily=0;$weekly=0;
    foreach($orders as $order){$day=substr((string)($order['raw_day']??''),0,10);if($day===$today->format('Y-m-d'))$daily++;if($day!==''&&$day>=$weekStart->format('Y-m-d')&&$day<=$weekEnd->format('Y-m-d'))$weekly++;}
    return [$daily,$weekly];
}

function report_trend_from_orders(array $orders): array {
    $today=new DateTimeImmutable('today');$trend=[];
    for($i=6;$i>=0;$i--){$d=$today->modify("-$i days");$key=$d->format('Y-m-d');$count=0;foreach($orders as $order)if(substr((string)($order['raw_day']??''),0,10)===$key)$count++;$trend[]=['date'=>$key,'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>$count];}
    return $trend;
}

function load_all_technician_reports_php(int $viewerTelegramId): array {
    $orders=[];$seen=[];
    foreach(report_filter_technicians() as $tech){$tid=(int)($tech['telegram_id']??0);if($tid<=0)continue;$payload=load_my_report_php($tid);if(!($payload['ok']??false))continue;foreach(($payload['orders']??[]) as $order){$service=norm_key($order['service_number']??'');if($service==='')continue;$key=$tech['nik'].'|'.$service;if(isset($seen[$key]))continue;$seen[$key]=1;$order['technician_nik']=$tech['nik'];$order['technician_name']=$tech['name'];$orders[]=$order;}}
    usort($orders,fn($a,$b)=>strcmp((string)($b['raw_day']??''),(string)($a['raw_day']??'')) ?: strcmp((string)($a['technician_name']??''),(string)($b['technician_name']??'')) ?: strcmp((string)($a['service_number']??''),(string)($b['service_number']??'')));
    [$daily,$weekly]=report_week_counts($orders);
    return ['ok'=>true,'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'ALL'],'daily'=>$daily,'weekly'=>$weekly,'all'=>count($orders),'orders'=>$orders,'trend'=>report_trend_from_orders($orders),'backend'=>'php'];
}

function load_report_for_viewer_php(int $viewerTelegramId,string $targetNik=''): array {
    $viewer=technician_by_telegram($viewerTelegramId);if(!$viewer)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $viewer=report_canonical_technician($viewer);$supervisor=report_is_supervisor($viewer);$target=trim($targetNik);
    if(!$supervisor){
        if($target!==''&&$target!==trim((string)($viewer['nik']??'')))return['ok'=>false,'error'=>'forbidden','message'=>'Anda tidak memiliki akses laporan teknisi lain.'];
        $payload=load_my_report_php($viewerTelegramId);
        if($payload['ok']??false)$payload['technician']=report_canonical_technician($payload['technician']);
    } elseif($target===''||strtoupper($target)==='ALL') {$payload=load_all_technician_reports_php($viewerTelegramId);}
    else {$tech=report_target_by_nik($target);if(!$tech)return['ok'=>false,'error'=>'technician_not_found','message'=>'NIK teknisi tidak ditemukan.'];$tid=(int)($tech['telegram_id']??0);if($tid<=0)return['ok'=>false,'error'=>'technician_not_linked','message'=>'Teknisi belum terhubung ke akun Telegram.'];$payload=load_my_report_php($tid);if($payload['ok']??false){$payload['technician']['name']=$tech['name'];$payload['technician']['nik']=$tech['nik'];$payload['technician']['sto']=$tech['sto'];foreach($payload['orders'] as &$order){$order['technician_nik']=(string)$tech['nik'];$order['technician_name']=(string)$tech['name'];}unset($order);}}
    if(!($payload['ok']??false))return$payload;
    $payload['viewer']=['telegram_id'=>$viewerTelegramId,'nik'=>(string)($viewer['nik']??''),'name'=>(string)($viewer['name']??'-'),'sto'=>strtoupper(trim((string)($viewer['sto']??'')))];
    $payload['supervisor']=$supervisor;$payload['can_filter_nik']=$supervisor;$payload['selected_nik']=$supervisor?($target===''?'ALL':strtoupper($target)):(string)($viewer['nik']??'');$payload['technicians']=$supervisor?report_filter_technicians():[];
    return$payload;
}


/**
 * HSA INJOKO web report. This web account is not a Telegram technician, so
 * the report must read the dedicated INJOKO Google Sheet directly.
 */
function load_hsa_injoko_report_php(bool $force=false): array {
    try {
        $refs=orderanku_fetch_injoko_sheet($force);
        $items=[];
        foreach($refs as $row){
            $items[]=[
                'service_number'=>(string)($row['service_number']??''),
                'inet'=>(string)($row['service_number']??''),
                'customer_name'=>(string)($row['customer_name']??''),
                'name'=>(string)($row['customer_name']??''),
                'address'=>(string)($row['address']??''),
                'status'=>(string)($row['status']??'OPEN'),
                'assigned_technician'=>(string)($row['assigned_technician']??''),
                'rca'=>(string)($row['rca']??''),
                'date'=>'',
                'completed_at'=>'',
            ];
        }
        usort($items,fn($a,$b)=>strnatcasecmp((string)$a['service_number'],(string)$b['service_number']));
        // The INJOKO source sheet currently exposes WO status but no reliable
        // completion timestamp, therefore today/week remain zero instead of
        // fabricating dates from unrelated columns.
        return [
            'ok'=>true,
            'source'=>'GOOGLE SHEETS INJOKO',
            'today'=>0,
            'week'=>0,
            'all'=>count($items),
            'items'=>$items,
            'data'=>$items,
        ];
    } catch (Throwable $e) {
        error_log('[injoko-report] '.$e->getMessage());
        return ['ok'=>false,'error'=>'injoko_sheet_unavailable','message'=>$e->getMessage()];
    }
}
