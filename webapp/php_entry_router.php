<?php

declare(strict_types=1);

$path=parse_url($_SERVER['REQUEST_URI']??'',PHP_URL_PATH)?:'';

// Fast path for the Mini App document and static assets.  Do this BEFORE
// loading the database/Google-Sheet PHP modules below: Telegram WebView must
// be able to receive index.html, JS and CSS without waiting for backend setup.
function entry_serve_static(string $file):never{
    $ext=strtolower(pathinfo($file,PATHINFO_EXTENSION));
    $types=['html'=>'text/html; charset=utf-8','js'=>'application/javascript; charset=utf-8','css'=>'text/css; charset=utf-8','json'=>'application/json; charset=utf-8','svg'=>'image/svg+xml','png'=>'image/png','jpg'=>'image/jpeg','jpeg'=>'image/jpeg','webp'=>'image/webp','ico'=>'image/x-icon'];
    header('Content-Type: '.($types[$ext]??'application/octet-stream'));
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    header('Pragma: no-cache');
    header('Expires: 0');
    readfile($file);
    exit;
}

if($path==='/'||$path==='/index.html') entry_serve_static(__DIR__.'/index.html');

if(!str_starts_with($path,'/api/') && $path!=='/health' && $path!=='/website' && $path!=='/website/' && $path!=='/login' && $path!=='/login/' && $path!=='/web' && $path!=='/web/') {
    $candidate=realpath(__DIR__.$path);
    $base=realpath(__DIR__);
    if($candidate&&$base&&str_starts_with($candidate,$base.DIRECTORY_SEPARATOR)&&is_file($candidate)) entry_serve_static($candidate);
}

if($path==='/api/technician-profile') {
    require_once __DIR__.'/php_backend.php';
    require_once __DIR__.'/php_technician_master.php';
    require_once __DIR__.'/php_technician_profile.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try {
        $method=strtoupper($_SERVER['REQUEST_METHOD']??'GET');
        if($method==='GET') {
            $raw=trim((string)($_GET['telegram_id']??''));
            if(!ctype_digit($raw)) { http_response_code(400); echo json_encode(['ok'=>false,'error'=>'telegram_id_required']); exit; }
            $result=technician_profile_get((int)$raw);
            http_response_code(($result['ok']??false)?200:404);
            echo json_encode($result,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES); exit;
        }
        if($method==='POST') {
            $payload=json_decode(file_get_contents('php://input')?:'{}',true);
            $result=technician_profile_save(is_array($payload)?$payload:[]);
            http_response_code(($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:400));
            echo json_encode($result,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES); exit;
        }
        http_response_code(405); echo json_encode(['ok'=>false,'error'=>'method_not_allowed']); exit;
    } catch(Throwable $e) {
        error_log('[miniapp-php] technician profile: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
        http_response_code(500);
        echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Profil gagal diproses.']); exit;
    }
}

if($path==='/api/technician-master' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
    require_once __DIR__.'/php_backend.php';
    require_once __DIR__.'/php_technician_master.php';
    require_once __DIR__.'/php_technician_master_fast.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try {
        $raw=trim((string)($_GET['telegram_id']??''));
        if(!ctype_digit($raw)){http_response_code(400);echo json_encode(['ok'=>false,'error'=>'telegram_id_required']);exit;}
        $result=technician_master_for_viewer_fast((int)$raw);
        http_response_code(($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404));
        echo json_encode($result,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;
    } catch(Throwable $e) {
        error_log('[miniapp-php] technician master fast read: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
        http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Master Teknisi gagal dimuat.']);exit;
    }
}

require_once __DIR__.'/php_backend.php';
require_once __DIR__.'/php_compat.php';
require_once __DIR__.'/php_orderanku_fix.php';
require_once __DIR__.'/php_supervisor_report.php';
require_once __DIR__.'/php_injoko_dashboard.php';

function hsa_injoko_manager(int $id): array {
    $v=technician_by_telegram($id);if(!$v)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar.'];
    $nik=trim((string)($v['nik']??''));
    if($nik!=='86240021' && !(function_exists('report_is_supervisor')&&report_is_supervisor($v)))return['ok'=>false,'error'=>'forbidden','message'=>'Akses HSA/OSA saja.'];
    return['ok'=>true,'viewer'=>$v];
}
function hsa_injoko_data(bool $force=false): array {
    $rows=orderanku_fetch_injoko_sheet($force);[$bs,$bt]=orderanku_injoko_close_matches();$open=[];$close=[];$seen=[];
    foreach($rows as $r){
        $s=preg_replace('/\D+/','',(string)($r['service_number']??''))?:'';$t=norm_key($r['ticket_id']??'');
        $m=$s!==''&&isset($bs[$s])?$bs[$s]:($t!==''&&isset($bt[$t])?$bt[$t]:null);
        if($m){$k=$s!==''?'S:'.$s:($t!==''?'T:'.$t:'');if($k!==''&&!isset($seen[$k])){$o=order_payload($r);$o['status']='CLOSE';$o['close_report_date']=$m['report_date']??'';$o['close_technician_name']=$m['technician_name']??'';$o['close_technician_nik']=$m['technician_nik']??'';$o['close_description']=$m['description']??'';$close[]=$o;$seen[$k]=1;}continue;}
        if(orderanku_sheet_bucket($r)==='open'){$o=order_payload($r);$o['status']='OPEN';$open[]=$o;}
    }
    $all=array_merge($close,$open);return['ok'=>true,'summary'=>['total'=>count($all),'open'=>count($open),'close'=>count($close)],'orders'=>$all,'open_orders'=>$open,'close_orders'=>$close];
}
function hsa_injoko_reports(): array {
    if(!table_exists('injoko_close_reports'))return['ok'=>true,'summary'=>['today'=>0,'week'=>0,'all'=>0,'technicians'=>0],'leaders'=>[],'items'=>[]];
    $rows=db()->query("SELECT report_date,technician_nik,technician_name,ticket_id,service_number,old_sn,new_sn,valins_id,result,description FROM injoko_close_reports WHERE UPPER(TRIM(COALESCE(result,''))) IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED') ORDER BY id DESC")->fetchAll();
    $items=[];$seen=[];foreach($rows as $r){$nik=trim((string)($r['technician_nik']??''));$service=norm_key($r['service_number']??'');$ticket=norm_key($r['ticket_id']??'');$k=$nik.'|'.($service!==''?$service:$ticket);if($nik===''||($service===''&&$ticket==='')||isset($seen[$k]))continue;$seen[$k]=1;$r['_date']=injoko_history_date((string)($r['report_date']??''));$items[]=$r;}
    $today=(new DateTimeImmutable('today'))->format('Y-m-d');[$weekStart,$weekEnd]=period_bounds(new DateTimeImmutable('today'));$weekStart=$weekStart->format('Y-m-d');$weekEnd=$weekEnd->format('Y-m-d');
    $todayItems=[];$weekItems=[];$leaders=[];
    foreach($items as $r){$date=(string)($r['_date']??'');if($date===$today)$todayItems[$r['_date'].'|'.($r['technician_nik']??'').'|'.($r['service_number']??$r['ticket_id']??'')]=1;if($date!==''&&$date>=$weekStart&&$date<=$weekEnd)$weekItems[$r['_date'].'|'.($r['technician_nik']??'').'|'.($r['service_number']??$r['ticket_id']??'')]=1;$k=trim((string)$r['technician_nik']);$leaders[$k]??=['nik'=>$k,'name'=>(string)($r['technician_name']??''),'close'=>0];$leaders[$k]['close']++;}
    foreach($items as &$r)unset($r['_date']);unset($r);
    usort($leaders,fn($a,$b)=>$b['close']<=>$a['close']?:strcmp($a['name'],$b['name']));
    return['ok'=>true,'summary'=>['today'=>count($todayItems),'week'=>count($weekItems),'all'=>count($items),'technicians'=>count($leaders)],'leaders'=>array_values($leaders),'items'=>$items];
}

if($path==='/api/hsa-injoko-orders' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try{$raw=trim((string)($_GET['telegram_id']??''));if(!ctype_digit($raw)){http_response_code(400);echo json_encode(['ok'=>false,'error'=>'telegram_id_required']);exit;}$auth=hsa_injoko_manager((int)$raw);if(!($auth['ok']??false)){http_response_code(403);echo json_encode($auth);exit;}echo json_encode(hsa_injoko_data(((string)($_GET['force']??'0'))==='1'),JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}catch(Throwable $e){error_log('[miniapp-php] hsa injoko orders: '.$e->getMessage());http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Order INJOKO gagal dimuat.']);exit;}
}
if($path==='/api/hsa-injoko-report' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
    try{$raw=trim((string)($_GET['telegram_id']??''));if(!ctype_digit($raw)){http_response_code(400);echo json_encode(['ok'=>false,'error'=>'telegram_id_required']);exit;}$auth=hsa_injoko_manager((int)$raw);if(!($auth['ok']??false)){http_response_code(403);echo json_encode($auth);exit;}echo json_encode(hsa_injoko_reports(),JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}catch(Throwable $e){error_log('[miniapp-php] hsa injoko report: '.$e->getMessage());http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Laporan INJOKO gagal dimuat.']);exit;}
}

if($path==='/api/dashboard' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
    require_once __DIR__.'/php_dashboard_identity_readonly.php';
    header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try{$area=strtoupper(trim((string)($_GET['area']??'ALL')));$period=strtolower(trim((string)($_GET['period']??'daily')));$payload=($area==='ALL'||$area==='IJK')?load_injoko_dashboard_php($area,$period):load_dashboard_php($area,$period);echo json_encode(dashboard_identity_fill_missing_nik($payload),JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}catch(Throwable $e){error_log('[miniapp-php] dashboard identity read: '.$e->getMessage().' @ '.$e->getLine());http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Dashboard gagal dimuat.']);exit;}
}

if($path==='/api/technician' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
    require_once __DIR__.'/php_dashboard_identity_readonly.php';require_once __DIR__.'/php_technician_detail_readonly.php';header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try{$key=trim((string)($_GET['key']??''));if($key===''){http_response_code(400);echo json_encode(['ok'=>false,'error'=>'key_required']);exit;}$area=strtoupper(trim((string)($_GET['area']??'ALL')));$payload=($area==='ALL'||$area==='IJK')?load_injoko_technician_detail_php($key,$area):technician_detail_readonly($key,$area);echo json_encode($payload,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;}catch(Throwable $e){error_log('[miniapp-php] technician detail canonical read: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Detail teknisi gagal dimuat.']);exit;}
}

require __DIR__.'/php_router.php';
