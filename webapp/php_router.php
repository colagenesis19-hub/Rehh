<?php

declare(strict_types=1);
require __DIR__ . '/php_backend.php';
require __DIR__ . '/php_compat.php';
require __DIR__ . '/php_manja.php';
require __DIR__ . '/php_orderanku_fix.php';
require __DIR__ . '/php_dismantle.php';
require __DIR__ . '/php_supervisor_report.php';
require __DIR__ . '/php_supervisor_orders.php';
require __DIR__ . '/php_unified_workflow.php';
require __DIR__ . '/php_technician_master.php';
require __DIR__ . '/php_technician_profile.php';
require __DIR__ . '/php_technician_master_bootstrap.php';
require __DIR__ . '/php_assign_wo.php';
require __DIR__ . '/php_web_auth.php';

function respond(mixed $payload, int $status=200): never {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function input_json(): array {
    $raw = file_get_contents('php://input') ?: '{}';
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function serve_static_no_cache(string $file): never {
    $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
    $types = ['html'=>'text/html; charset=utf-8','js'=>'application/javascript; charset=utf-8','css'=>'text/css; charset=utf-8','json'=>'application/json; charset=utf-8','svg'=>'image/svg+xml','png'=>'image/png','jpg'=>'image/jpeg','jpeg'=>'image/jpeg','webp'=>'image/webp','ico'=>'image/x-icon'];
    header('Content-Type: ' . ($types[$ext] ?? 'application/octet-stream'));
    header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
    header('Pragma: no-cache'); header('Expires: 0'); readfile($file); exit;
}

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
if ($path === '/web' || $path === '/web/') serve_static_no_cache(__DIR__ . '/web/index.html');
if ($path === '/' || $path === '/index.html') serve_static_no_cache(__DIR__ . '/index.html');
if (!str_starts_with($path, '/api/') && $path !== '/health') {
    $candidate = realpath(__DIR__ . $path); $base = realpath(__DIR__);
    if ($candidate && $base && str_starts_with($candidate, $base . DIRECTORY_SEPARATOR) && is_file($candidate)) serve_static_no_cache($candidate);
    http_response_code(404); echo 'Not Found'; exit;
}

try {
    if ($method === 'GET' && $path === '/health') respond(['ok'=>true,'backend'=>'php','php'=>PHP_VERSION,'database'=>db_path()]);

    // HSA web console authentication. Credentials never come from the browser except login input.
    if ($method === 'POST' && $path === '/api/web-login') {
        $result=web_auth_login(input_json());
        respond($result,($result['ok']??false)?200:401);
    }
    if ($method === 'GET' && $path === '/api/web-session') {
        $user=web_auth_hsa();
        respond($user?['ok'=>true,'user'=>$user]:['ok'=>false,'error'=>'web_auth_required'], $user?200:401);
    }
    if ($method === 'POST' && $path === '/api/web-logout') respond(web_auth_logout());
    if ($method === 'GET' && $path === '/api/web-hsa-data') {
        $user=web_auth_require_hsa();
        $result=assign_wo_list((int)($user['telegram_id']??0));
        respond($result,($result['ok']??false)?200:500);
    }
    if ($method === 'POST' && $path === '/api/web-hsa-assign') {
        $user=web_auth_require_hsa();
        $payload=input_json();
        $payload['telegram_id']=(int)($user['telegram_id']??0);
        $result=assign_wo_apply($payload);
        respond($result,($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:400));
    }

    if ($method === 'GET' && $path === '/api/dashboard') respond(load_dashboard_php((string)($_GET['area'] ?? 'ALL'), (string)($_GET['period'] ?? 'daily')));
    if ($method === 'GET' && $path === '/api/rca-summary') respond(load_rca_summary_php((string)($_GET['area'] ?? 'ALL')));
    if ($method === 'GET' && $path === '/api/technician') {
        $key = trim((string)($_GET['key'] ?? $_GET['nik'] ?? ''));
        if ($key === '') respond(['error'=>'key required'], 400);
        if (!str_starts_with($key,'NAME:') && !str_starts_with($key,'NIK:')) $key='NIK:'.norm_key($key);
        respond(load_technician($key,(string)($_GET['area'] ?? 'ALL')));
    }
    if ($method === 'GET' && $path === '/api/technician-profile') {
        $raw=trim((string)($_GET['telegram_id'] ?? '')); if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=technician_profile_get((int)$raw); respond($result,($result['ok']??false)?200:404);
    }
    if ($method === 'POST' && $path === '/api/technician-profile') {
        $result=technician_profile_save(input_json()); respond($result,($result['ok']??false)?200:400);
    }
    if ($method === 'GET' && $path === '/api/technician-master') {
        technician_master_bootstrap();
        $raw=trim((string)($_GET['telegram_id'] ?? '')); if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=technician_master_for_viewer((int)$raw); respond($result,($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404));
    }
    if ($method === 'POST' && $path === '/api/technician-master') {
        technician_master_bootstrap();
        $result=save_technician_master(input_json()); respond($result,($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:400));
    }
    if ($method === 'POST' && $path === '/api/technician-master/normalize') {
        technician_master_bootstrap();
        $p=input_json();$raw=trim((string)($p['telegram_id']??'')); if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'invalid_request'],400);
        $viewer=technician_by_telegram((int)$raw); if(!$viewer||!report_is_supervisor($viewer))respond(['ok'=>false,'error'=>'forbidden'],403);
        respond(normalize_technician_data());
    }
    if ($method === 'GET' && $path === '/api/assign-wo') {
        $raw=trim((string)($_GET['telegram_id'] ?? '')); if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=assign_wo_list((int)$raw); respond($result,($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:500));
    }
    if ($method === 'POST' && $path === '/api/assign-wo') {
        $result=assign_wo_apply(input_json()); respond($result,($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:400));
    }
    if ($method === 'GET' && $path === '/api/my-open-orders') {
        $raw=trim((string)($_GET['telegram_id'] ?? '')); if (!ctype_digit($raw)) respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=load_orders_for_viewer_php((int)$raw,(string)($_GET['target_nik'] ?? ''),((string)($_GET['force'] ?? '0')) === '1');
        if ($result['ok'] ?? false) $result=unified_enrich_open_orders_result($result,(int)$raw);
        $status=($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404); respond($result,$status);
    }
    if ($method === 'GET' && $path === '/api/dismantle-orders') {
        $raw=trim((string)($_GET['telegram_id'] ?? '')); if (!ctype_digit($raw)) respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=load_dismantle_for_viewer_php((int)$raw,(string)($_GET['target_nik'] ?? '')); $status=($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404); respond($result,$status);
    }
    if ($method === 'POST' && $path === '/api/dismantle-orders/complete') {$result=complete_dismantle_order(input_json());respond($result,$result['ok']?200:400);}
    if ($method === 'GET' && $path === '/api/open-order-search') {
        $raw=trim((string)($_GET['telegram_id'] ?? ''));if (!ctype_digit($raw)) respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=search_open_orders((int)$raw,(string)($_GET['q'] ?? ''),((string)($_GET['force'] ?? '0'))==='1');$status=$result['ok']?200:(($result['error']??'')==='query_too_short'?400:404);respond($result,$status);
    }
    if ($method === 'GET' && $path === '/api/manja') {$raw=trim((string)($_GET['telegram_id'] ?? ''));if (!ctype_digit($raw)) respond(['ok'=>false,'error'=>'telegram_id_required'],400);$result=load_manja_for_technician((int)$raw);respond($result,$result['ok']?200:404);}
    if ($method === 'POST' && $path === '/api/manja') {$result=save_manja_from_miniapp(input_json());respond($result,$result['ok']?200:400);}
    if ($method === 'GET' && $path === '/api/my-report') {
        $raw=trim((string)($_GET['telegram_id'] ?? ''));if (!ctype_digit($raw)) respond(['ok'=>false,'error'=>'telegram_id_required'],400);
        $result=load_report_for_viewer_php((int)$raw,(string)($_GET['target_nik'] ?? ''));$status=($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404);respond($result,$status);
    }
    if ($method === 'GET' && $path === '/api/unified-workflow') {$raw=trim((string)($_GET['telegram_id'] ?? ''));if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);$result=unified_get_workflow_state((int)$raw,(string)($_GET['service_number']??''),(string)($_GET['ticket_id']??''));$status=($result['ok']??false)?200:(($result['error']??'')==='forbidden'?403:404);respond($result,$status);}
    if ($method === 'POST' && $path === '/api/unified-workflow') {$result=unified_sync_workflow_payload(input_json());respond($result,($result['ok']??false)?200:400);}
    if ($method === 'GET' && $path === '/api/workflow-drafts') {$raw=trim((string)($_GET['telegram_id']??''));if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);$result=load_workflow_drafts((int)$raw);respond($result,$result['ok']?200:404);}
    if ($method === 'POST' && $path === '/api/workflow-drafts') {$payload=input_json();$result=save_workflow_draft($payload);if($result['ok']??false){$sync=unified_sync_workflow_payload($payload);$result['unified_sync']=$sync['ok']??false;$result['master_updated_at']=$sync['updated_at']??null;}respond($result,$result['ok']?200:400);}
    if ($method === 'DELETE' && $path === '/api/workflow-drafts') {$raw=trim((string)($_GET['telegram_id']??''));if(!ctype_digit($raw))respond(['ok'=>false,'error'=>'telegram_id_required'],400);respond(delete_workflow_draft((int)$raw,(string)($_GET['action']??''),(string)($_GET['service_number']??'')));}
    if ($method === 'GET' && $path === '/api/workflow-history') {$raw=trim((string)($_GET['telegram_id']??''));$service=trim((string)($_GET['service_number']??''));if(!ctype_digit($raw)||$service==='')respond(['ok'=>false,'error'=>'invalid_request'],400);respond(['ok'=>true,'service_number'=>$service,'items'=>workflow_history((int)$raw,$service)]);}
    if ($method === 'POST' && $path === '/api/workflow-history') {$p=input_json();$raw=(string)($p['telegram_id']??'');$hid=(string)($p['history_id']??'');if(!ctype_digit($raw)||!ctype_digit($hid))respond(['ok'=>false,'error'=>'invalid_request'],400);$ok=update_history((int)$raw,(int)$hid,(string)($p['content']??''));respond(['ok'=>$ok],$ok?200:404);}
    if ($method === 'POST' && $path === '/api/workflow-complete') {$payload=input_json();$sync=unified_sync_workflow_payload($payload);$result=complete_workflow($payload);$result['unified_sync']=$sync['ok']??false;respond($result,$result['ok']?200:400);}
    respond(['ok'=>false,'error'=>'not_found','path'=>$path],404);
} catch (Throwable $e) {
    error_log('[miniapp-php] '.$e->getMessage().' @ '.$e->getFile().':'.$e->getLine());
    if ($e->getMessage()==='WEB_AUTH_REQUIRED') respond(['ok'=>false,'error'=>'web_auth_required','message'=>'Silakan login sebagai HSA.'],401);
    respond(['ok'=>false,'error'=>'internal_error','message'=>'Mini App backend gagal memproses permintaan.'],500);
}