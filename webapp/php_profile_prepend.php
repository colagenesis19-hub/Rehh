<?php

declare(strict_types=1);

$profilePath=parse_url($_SERVER['REQUEST_URI']??'',PHP_URL_PATH)?:'';
if($profilePath!=='/api/technician-profile') return;

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
        http_response_code(($result['ok']??false)?200:400);
        echo json_encode($result,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES); exit;
    }
    http_response_code(405); echo json_encode(['ok'=>false,'error'=>'method_not_allowed']); exit;
} catch(Throwable $e) {
    error_log('[miniapp-php] technician profile: '.$e->getMessage());
    http_response_code(500);
    echo json_encode(['ok'=>false,'error'=>'internal_error','message'=>'Profil gagal diproses.']); exit;
}
