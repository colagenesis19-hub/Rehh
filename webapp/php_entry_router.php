<?php

declare(strict_types=1);

$path=parse_url($_SERVER['REQUEST_URI']??'',PHP_URL_PATH)?:'';
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

if($path==='/api/dashboard' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
    require_once __DIR__.'/php_backend.php';
    require_once __DIR__.'/php_compat.php';
    require_once __DIR__.'/php_injoko_dashboard.php';
    require_once __DIR__.'/php_dashboard_identity_readonly.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try {
        $area=strtoupper(trim((string)($_GET['area']??'ALL')));
        $period=strtolower(trim((string)($_GET['period']??'daily')));
        $payload=($area==='ALL'||$area==='IJK')
            ? load_injoko_dashboard_php($area,$period)
            : load_dashboard_php($area,$period);
        echo json_encode(dashboard_identity_fill_missing_nik($payload),JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;
    } catch(Throwable $e) {
        error_log('[miniapp-php] dashboard identity read: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
        http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Dashboard gagal dimuat.']);exit;
    }
}

if($path==='/api/technician' && strtoupper($_SERVER['REQUEST_METHOD']??'GET')==='GET') {
    require_once __DIR__.'/php_backend.php';
    require_once __DIR__.'/php_dashboard_identity_readonly.php';
    require_once __DIR__.'/php_technician_detail_readonly.php';
    require_once __DIR__.'/php_injoko_dashboard.php';
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    try {
        $key=trim((string)($_GET['key']??''));
        if($key===''){http_response_code(400);echo json_encode(['ok'=>false,'error'=>'key_required']);exit;}
        $area=strtoupper(trim((string)($_GET['area']??'ALL')));
        $payload=($area==='ALL'||$area==='IJK')
            ? load_injoko_technician_detail_php($key,$area)
            : technician_detail_readonly($key,$area);
        echo json_encode($payload,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES);exit;
    } catch(Throwable $e) {
        error_log('[miniapp-php] technician detail canonical read: '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
        http_response_code(500);echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Detail teknisi gagal dimuat.']);exit;
    }
}

require __DIR__.'/php_router.php';
