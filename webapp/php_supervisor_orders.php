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
    foreach (report_filter_technicians() as $tech) {
        $tid=(int)($tech['telegram_id'] ?? 0); if ($tid<=0) continue;
        $payload=load_my_open_orders_fixed($tid,$force); if (!($payload['ok'] ?? false)) continue;
        $payload=decorate_supervisor_order_payload($payload,$tech);
        foreach (($payload['areas'] ?? []) as $area) {
            $name=(string)($area['area'] ?? 'LAINNYA');
            $byArea[$name] ??= ['area'=>$name,'open'=>0,'close'=>0,'update'=>0,'orders'=>[]];
            $byArea[$name]['open'] += (int)($area['open'] ?? 0);
            $byArea[$name]['close'] += (int)($area['close'] ?? 0);
            $byArea[$name]['update'] += (int)($area['update'] ?? 0);
            foreach (($area['orders'] ?? []) as $order) $byArea[$name]['orders'][]=$order;
        }
    }
    $areas=array_values($byArea);
    foreach($areas as &$area) usort($area['orders'],fn($a,$b)=>strcmp((string)($a['technician_name']??''),(string)($b['technician_name']??'')) ?: strnatcasecmp((string)($a['address']??''),(string)($b['address']??'')));
    unset($area);
    usort($areas,fn($a,$b)=>($a['area']==='JAGIR'?1:0)<=>($b['area']==='JAGIR'?1:0) ?: strcmp($a['area'],$b['area']));
    return ['ok'=>true,'technician'=>['telegram_id'=>0,'nik'=>'ALL','name'=>'SEMUA TEKNISI','sto'=>'ALL'],'source'=>'ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)','total_open'=>array_sum(array_column($areas,'open')),'active_areas'=>count($areas),'areas'=>$areas];
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
