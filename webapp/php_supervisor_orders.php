<?php

declare(strict_types=1);

function order_target_by_nik(string $nik): ?array { return report_target_by_nik($nik); }

function decorate_supervisor_order_payload(array $payload, array $tech): array {
    foreach (($payload['areas'] ?? []) as &$area) {
        foreach (($area['orders'] ?? []) as &$order) {
            $order['technician_nik'] = (string)($tech['nik'] ?? '');
            $order['technician_name'] = (string)($tech['name'] ?? '-');
        }
        unset($order);
    }
    unset($area);
    return $payload;
}

function merge_all_open_orders_php(bool $force=false): array {
    $byArea=[];
    $techStats=[];
    $grand=['open'=>0,'close'=>0,'update'=>0];

    foreach (report_filter_technicians() as $tech) {
        $tid=(int)($tech['telegram_id'] ?? 0); if($tid<=0) continue;
        $payload=load_my_open_orders_fixed($tid,$force); if (!($payload['ok'] ?? false)) continue;
        $payload=decorate_supervisor_order_payload($payload,$tech);

        $stat=['nik'=>(string)($tech['nik']??''),'name'=>(string)($tech['name']??'-'),'sto'=>(string)($tech['sto']??''),'open'=>0,'close'=>0,'update'=>0,'total'=>0];
        foreach (($payload['areas'] ?? []) as $area) {
            $name=(string)($area['area'] ?? 'LAINNYA');
            $open=(int)($area['open'] ?? 0); $close=(int)($area['close'] ?? 0); $update=(int)($area['update'] ?? 0);
            $byArea[$name] ??= ['area'=>$name,'open'=>0,'close'=>0,'update'=>0,'orders'=>[]];
            $byArea[$name]['open'] += $open; $byArea[$name]['close'] += $close; $byArea[$name]['update'] += $update;
            foreach (($area['orders'] ?? []) as $order) $byArea[$name]['orders'][]=$order;
            $stat['open'] += $open; $stat['close'] += $close; $stat['update'] += $update;
        }
        $stat['total']=$stat['open']+$stat['close']+$stat['update'];
        $techStats[]=$stat;
        $grand['open'] += $stat['open']; $grand['close'] += $stat['close']; $grand['update'] += $stat['update'];
    }

    usort($techStats,fn($a,$b)=>($b['total']<=>$a['total']) ?: strcasecmp($a['name'],$b['name']));
    $areas=array_values($byArea);
    foreach($areas as &$area) usort($area['orders'],fn($a,$b)=>strcmp((string)($a['technician_name']??''),(string)($b['technician_name']??'')) ?: strnatcasecmp((string)($a['address']??''),(string)($b['address']??'')));
    unset($area);
    usort($areas,fn($a,$b)=>($a['area']==='JAGIR'?1:0)<=>($b['area']==='JAGIR'?1:0) ?: strcmp($a['area'],$b['area']));

    return [
        'ok'=>true,
        'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'ALL'],
        'source'=>'INJOKO • REPLACEMENT',
        'total_count'=>$grand['open']+$grand['close']+$grand['update'],
        'total_open'=>$grand['open'],
        'total_close'=>$grand['close'],
        'total_update'=>$grand['update'],
        'active_areas'=>count($areas),
        'technician_stats'=>$techStats,
        'areas'=>$areas
    ];
}

function load_orders_for_viewer_php(int $viewerTelegramId,string $targetNik='',bool $force=false): array {
    $viewer=technician_by_telegram($viewerTelegramId); if(!$viewer)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $supervisor=report_is_supervisor($viewer); $target=trim($targetNik);
    if(!$supervisor){
        if($target!==''&&$target!==trim((string)($viewer['nik']??'')))return['ok'=>false,'error'=>'forbidden','message'=>'Anda tidak memiliki akses order teknisi lain.'];
        $payload=load_my_open_orders_fixed($viewerTelegramId,$force);
    } elseif($target===''||strtoupper($target)==='ALL') {
        $payload=merge_all_open_orders_php($force);
    } else {
        $tech=order_target_by_nik($target); if(!$tech)return['ok'=>false,'error'=>'technician_not_found','message'=>'NIK teknisi tidak ditemukan.'];
        $tid=(int)($tech['telegram_id']??0); if($tid<=0)return['ok'=>false,'error'=>'technician_not_linked','message'=>'Teknisi belum terhubung ke akun Telegram.'];
        $payload=decorate_supervisor_order_payload(load_my_open_orders_fixed($tid,$force),$tech);
        $stat=['nik'=>(string)($tech['nik']??''),'name'=>(string)($tech['name']??'-'),'sto'=>(string)($tech['sto']??''),'open'=>0,'close'=>0,'update'=>0,'total'=>0];
        foreach(($payload['areas']??[]) as $area){$stat['open']+=(int)($area['open']??0);$stat['close']+=(int)($area['close']??0);$stat['update']+=(int)($area['update']??0);}
        $stat['total']=$stat['open']+$stat['close']+$stat['update'];
        $payload['technician_stats']=[$stat];
        $payload['total_count']=$stat['total']; $payload['total_open']=$stat['open']; $payload['total_close']=$stat['close']; $payload['total_update']=$stat['update'];
        $payload['source']='INJOKO • REPLACEMENT';
    }
    if(!($payload['ok']??false))return$payload;
    $payload['viewer']=['telegram_id'=>$viewerTelegramId,'nik'=>(string)($viewer['nik']??''),'name'=>(string)($viewer['name']??'-')];
    $payload['supervisor']=$supervisor; $payload['read_only']=$supervisor; $payload['can_filter_nik']=$supervisor;
    $payload['selected_nik']=$supervisor?($target===''?'ALL':strtoupper($target)):(string)($viewer['nik']??'');
    $payload['technicians']=$supervisor?report_filter_technicians():[];
    return$payload;
}

function dismantle_trend_merge(array $payloads): array {
    $map=[]; foreach($payloads as $payload)foreach(($payload['trend']??[]) as $item){$date=(string)($item['date']??'');if($date==='')continue;$map[$date]??=['date'=>$date,'label'=>(string)($item['label']??''),'total'=>0];$map[$date]['total']+=(int)($item['total']??0);} ksort($map); return array_values($map);
}

function load_dismantle_for_viewer_php(int $viewerTelegramId,string $targetNik=''): array {
    $viewer=technician_by_telegram($viewerTelegramId); if(!$viewer)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $supervisor=report_is_supervisor($viewer); $target=trim($targetNik);
    if(!$supervisor){
        if($target!==''&&$target!==trim((string)($viewer['nik']??'')))return['ok'=>false,'error'=>'forbidden','message'=>'Anda tidak memiliki akses dismantle teknisi lain.'];
        $payload=load_dismantle_orders($viewerTelegramId);
    } elseif($target!==''&&strtoupper($target)!=='ALL') {
        $tech=report_target_by_nik($target); if(!$tech)return['ok'=>false,'error'=>'technician_not_found','message'=>'NIK teknisi tidak ditemukan.'];
        $tid=(int)($tech['telegram_id']??0); if($tid<=0)return['ok'=>false,'error'=>'technician_not_linked','message'=>'Teknisi belum terhubung ke akun Telegram.'];
        $payload=load_dismantle_orders($tid);
    } else {
        $orders=[];$done=0;$parts=[];
        foreach(report_filter_technicians() as $tech){$tid=(int)($tech['telegram_id']??0);if($tid<=0)continue;$p=load_dismantle_orders($tid);if(!($p['ok']??false))continue;$parts[]=$p;$done+=(int)($p['done_count']??0);foreach(($p['orders']??[]) as $o){$o['technician_nik']=$tech['nik'];$o['technician_name']=$tech['name'];$orders[]=$o;}}
        $payload=['ok'=>true,'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'ALL'],'open_count'=>count($orders),'done_count'=>$done,'total_count'=>count($orders)+$done,'orders'=>$orders,'trend'=>dismantle_trend_merge($parts)];
    }
    if(!($payload['ok']??false))return$payload; $payload['supervisor']=$supervisor; $payload['read_only']=$supervisor; $payload['selected_nik']=$supervisor?($target===''?'ALL':strtoupper($target)):(string)($viewer['nik']??''); return$payload;
}


/**
 * HSA web view reads the Google Sheet directly. Do not depend on the local
 * report history or Telegram assignment mapping, otherwise newly imported or
 * unassigned WO rows disappear from the website.
 */
function load_hsa_orders_from_sheet_php(bool $force=false): array {
    $refs=orderanku_fetch_sheet($force);
    $grand=['open'=>0,'close'=>0,'update'=>0];
    $byArea=[];
    $techStats=[];

    foreach($refs as $row){
        // INJOKO web must never display MYR/JGR work orders.
        // Only rows explicitly belonging to STO IJK are part of this HSA view.
        if(strtoupper(trim((string)($row['sto']??'')))!=='IJK') continue;
        $bucket=orderanku_sheet_bucket($row);
        if(!isset($grand[$bucket])) $bucket='open';
        $grand[$bucket]++;

        $techName=trim((string)($row['assigned_technician']??''));
        $techKey=$techName!==''?norm_name($techName):'UNASSIGNED';
        if(!isset($techStats[$techKey])) $techStats[$techKey]=[
            'nik'=>'','name'=>$techName!==''?$techName:'BELUM DIASSIGN','sto'=>trim((string)($row['sto']??'')),
            'open'=>0,'close'=>0,'update'=>0,'total'=>0
        ];
        $techStats[$techKey][$bucket]++;
        $techStats[$techKey]['total']++;

        if($bucket!=='open') continue;
        $area='INJOKO';
        $byArea[$area]??=['area'=>$area,'open'=>0,'close'=>0,'update'=>0,'orders'=>[]];
        $order=order_payload($row);
        $order['area']=$area;
        $order['source']='GOOGLE SHEETS';
        $order['status']=trim((string)($row['status']??'OPEN'))?:'OPEN';
        $order['technician_name']=$techName!==''?$techName:'BELUM DIASSIGN';
        $order['technician_nik']='';
        $byArea[$area]['orders'][]=$order;
        $byArea[$area]['open']++;
    }

    $areas=array_values($byArea);
    foreach($areas as &$area) usort($area['orders'],fn($a,$b)=>strcasecmp((string)($a['technician_name']??''),(string)($b['technician_name']??'')) ?: strnatcasecmp((string)($a['address']??''),(string)($b['address']??'')));
    unset($area);
    $stats=array_values($techStats);
    usort($stats,fn($a,$b)=>($b['total']<=>$a['total']) ?: strcasecmp($a['name'],$b['name']));

    return [
        'ok'=>true,
        'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'INJOKO'],
        'source'=>'GOOGLE SHEETS (LIVE)',
        'total_count'=>$grand['open']+$grand['close']+$grand['update'],
        'total_open'=>$grand['open'],
        'total_close'=>$grand['close'],
        'total_update'=>$grand['update'],
        'active_areas'=>count($areas),
        'technician_stats'=>$stats,
        'areas'=>$areas
    ];
}
