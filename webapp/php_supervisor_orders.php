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

/** Build the HSA dashboard from the same dedicated INJOKO sheet as Orderanku. */
function load_hsa_injoko_dashboard_php(string $period='daily'): array {
    $refs=orderanku_fetch_injoko_sheet(true);
    $summary=['total_close'=>0,'total_open'=>0,'active_technicians'=>0,'average_close'=>0];
    $tech=[];$trend=[];
    foreach($refs as $row){
        $bucket=orderanku_sheet_bucket($row);
        if($bucket==='close') $summary['total_close']++;
        elseif($bucket==='update') {}
        else $summary['total_open']++;
        $name=trim((string)($row['assigned_technician']??''));
        if($name!==''){
            $key=norm_name($name);
            $tech[$key]??=['nik'=>'','name'=>$name,'total'=>0];
            if($bucket==='close') $tech[$key]['total']++;
        }
    }
    $leaders=array_values(array_filter($tech,fn($x)=>$x['total']>0));
    usort($leaders,fn($a,$b)=>($b['total']<=>$a['total'])?:strcasecmp($a['name'],$b['name']));
    $summary['active_technicians']=count($leaders);
    $summary['average_close']=$summary['active_technicians']>0 ? $summary['total_close']/$summary['active_technicians'] : 0;
    $total=$summary['total_close']+$summary['total_open'];
    $progress=$total>0 ? (int)round(($summary['total_close']/$total)*100) : 0;
    return ['ok'=>true,'source'=>'GOOGLE SHEETS INJOKO','period'=>$period,'summary'=>$summary,'open'=>$summary['total_open'],'progress'=>$progress,'trend'=>$trend,'leaderboard'=>$leaders];
}

function load_hsa_injoko_rca_php(): array {
    $refs=orderanku_fetch_injoko_sheet(true);$counts=[];
    foreach($refs as $row){$v=trim((string)($row['rca']??''));if($v==='')continue;$counts[$v]=($counts[$v]??0)+1;}
    $items=[];foreach($counts as $label=>$count)$items[]=['label'=>$label,'count'=>$count];
    usort($items,fn($a,$b)=>$b['count']<=>$a['count']);
    return ['ok'=>true,'source'=>'GOOGLE SHEETS INJOKO','items'=>$items];
}


function hsa_injoko_sheet_row(array $row): bool {
    // Prefer the STO carried by the live Google Sheet row.
    if(strtoupper(trim((string)($row['sto']??'')))==='IJK') return true;

    // Some WO rows in the sheet do not expose the STO column in the selected
    // range. Fall back to the locally synced WO/area mapping for that INET.
    $service=trim((string)($row['service_number']??''));
    if($service==='') return false;
    try {
        if(table_exists('orders')){
            $st=db()->prepare('SELECT sto FROM orders WHERE TRIM(service_number)=? ORDER BY id DESC LIMIT 1');
            $st->execute([$service]);
            if(strtoupper(trim((string)$st->fetchColumn()))==='IJK') return true;
        }
        if(table_exists('report_area_orders')){
            $st=db()->prepare('SELECT 1 FROM report_area_orders WHERE TRIM(service_number)=? AND UPPER(TRIM(sto_code))=? LIMIT 1');
            $st->execute([$service,'IJK']);
            if($st->fetchColumn()) return true;
        }
    } catch(Throwable) {}
    return false;
}

function load_hsa_orders_from_sheet_php(bool $force=false): array {
    $refs=orderanku_fetch_injoko_sheet($force);
    $grand=['open'=>0,'close'=>0,'update'=>0];
    $byArea=[];
    $techStats=[];

    foreach($refs as $row){
        // The source spreadsheet is the dedicated INJOKO WO sheet, so every
        // valid row belongs to the INJOKO view even when it has no STO column.
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


function hsa_kecamatan_normalize(string $value): string {
    $v = strtoupper(trim($value));
    $v = str_replace(['KECAMATAN','KEC.','KEC '], '', $v);
    $v = preg_replace('/[^A-Z0-9 ]+/', ' ', $v) ?: '';
    return trim(preg_replace('/\\s+/', ' ', $v) ?: '');
}

function hsa_kecamatan_from_address(string $address, string $explicit=''): string {
    // The INJOKO Order sheet is the source of truth. Use the Kecamatan
    // value read from that sheet; do not invent a district from the address.
    $explicit = hsa_kecamatan_normalize($explicit);
    return $explicit !== '' ? $explicit : 'TIDAK TERISI DI SHEET';
}

function load_hsa_order_map_php(bool $force=false): array {
    $refs = orderanku_fetch_injoko_sheet($force);
    $stats = [];
    $orders = [];
    $grand = ['open'=>0,'close'=>0,'update'=>0];
    foreach ($refs as $row) {
        $bucket = orderanku_sheet_bucket($row);
        if (!isset($grand[$bucket])) $bucket = 'open';
        $grand[$bucket]++;
        $kec = hsa_kecamatan_from_address((string)($row['address'] ?? ''), (string)($row['kecamatan'] ?? ''));
        if (!isset($stats[$kec])) $stats[$kec] = ['kecamatan'=>$kec,'total'=>0,'open'=>0,'close'=>0,'update'=>0,'success_rate'=>0];
        $stats[$kec]['total']++;
        $stats[$kec][$bucket]++;
        $o = order_payload($row, 'INJOKO');
        $o['status'] = trim((string)($row['status'] ?? 'OPEN')) ?: 'OPEN';
        $o['bucket'] = $bucket;
        $o['kecamatan'] = $kec;
        $o['technician_name'] = trim((string)($row['assigned_technician'] ?? '')) ?: 'BELUM DIASSIGN';
        $orders[] = $o;
    }
    foreach ($stats as &$s) $s['success_rate'] = $s['total'] > 0 ? round(($s['close'] / $s['total']) * 100, 1) : 0;
    unset($s);
    usort($stats, fn($a,$b) => ($b['total'] <=> $a['total']) ?: strcmp($a['kecamatan'],$b['kecamatan']));
    usort($orders, fn($a,$b) => strcmp((string)$a['kecamatan'],(string)$b['kecamatan']) ?: strnatcasecmp((string)$a['address'],(string)$b['address']));
    return [
        'ok'=>true,
        'source'=>'GOOGLE SHEETS INJOKO (LIVE)',
        'total'=>$grand['open']+$grand['close']+$grand['update'],
        'open'=>$grand['open'],'close'=>$grand['close'],'update'=>$grand['update'],
        'kecamatan'=>$stats,'orders'=>$orders,
        'polygon_source'=>'BIG • Batas Wilayah Administrasi Kecamatan'
    ];
}


function load_hsa_kecamatan_geojson_php(): array {
    $cache='/tmp/kerja-bot-surabaya-kecamatan-geojson.json';
    if(is_file($cache) && time()-filemtime($cache)<86400){$d=json_decode((string)file_get_contents($cache),true);if(is_array($d))return $d;}
    $url='https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/BATAS_WILAYAH/MapServer/3/query?where=wadmkk%3D%27Surabaya%27&outFields=wadmkc%2Cwadmkk%2Cwadmpr&returnGeometry=true&outSR=4326&f=geojson';
    $ctx=stream_context_create(['http'=>['timeout'=>20,'header'=>"User-Agent: MR-O-Apps/1.0\r\n"]]);
    $raw=@file_get_contents($url,false,$ctx);
    if($raw===false||trim($raw)==='') return ['ok'=>false,'error'=>'kecamatan_polygon_unavailable','message'=>'Data polygon kecamatan dari BIG tidak dapat diambil.'];
    $d=json_decode($raw,true);
    if(!is_array($d)||!isset($d['features'])) return ['ok'=>false,'error'=>'kecamatan_polygon_invalid','message'=>'Format polygon kecamatan dari BIG tidak valid.'];
    @file_put_contents($cache,json_encode($d,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES));
    return ['ok'=>true,'geojson'=>$d,'source'=>'BIG • Peta Wilayah Administrasi Kecamatan'];
}
