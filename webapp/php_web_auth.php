<?php

declare(strict_types=1);

function web_auth_start(): void {
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_name('INJOKO_WEB');
        session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>true,'httponly'=>true,'samesite'=>'Lax']);
        session_start();
    }
}
function web_auth_file(): string { return dirname(__DIR__) . '/database/web_auth.json'; }
function web_auth_load_users(): array {
    $data=is_file(web_auth_file())?json_decode((string)@file_get_contents(web_auth_file()),true):null;
    if(is_array($data)&&isset($data['users'])&&is_array($data['users'])) return $data['users'];
    if(is_array($data)&&!empty($data['password_hash'])) return ['86240021'=>['password_hash'=>(string)$data['password_hash'],'role'=>'HSA','must_change_password'=>false]];
    return [];
}
function web_auth_save_users(array $users): bool {
    $file=web_auth_file();$dir=dirname($file);
    if(!is_dir($dir)&&!@mkdir($dir,0775,true)&&!is_dir($dir))return false;
    $tmp=$file.'.tmp';$ok=@file_put_contents($tmp,json_encode(['version'=>2,'users'=>$users,'updated_at'=>date('c')],JSON_UNESCAPED_UNICODE|JSON_PRETTY_PRINT),LOCK_EX)!==false&&@rename($tmp,$file);
    if($ok)@chmod($file,0600);else @unlink($tmp);return $ok;
}
function technician_by_nik(string $nik): ?array {
    if(!table_exists('technicians'))return null;
    $st=db()->prepare('SELECT telegram_id,nik,name,sto FROM technicians WHERE TRIM(nik)=? LIMIT 1');$st->execute([trim($nik)]);$r=$st->fetch();return $r?:null;
}
function web_auth_role(string $nik): string { return $nik==='86240021'?'HSA':'TEKNISI'; }
function web_auth_login(array $payload): array {
    web_auth_start();$nik=preg_replace('/\D/','',(string)($payload['nik']??''))?:'';$password=(string)($payload['password']??'');
    $tech=technician_by_nik($nik);if(!$tech||$password==='')return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    $users=web_auth_load_users();$record=$users[$nik]??null;
    // First login uses NIK as temporary password, then forces a password change.
    if(!$record){if(!hash_equals($nik,$password))return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];$record=['password_hash'=>password_hash($password,PASSWORD_DEFAULT),'role'=>web_auth_role($nik),'must_change_password'=>true];$users[$nik]=$record;web_auth_save_users($users);}
    if(!password_verify($password,(string)($record['password_hash']??'')))return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    session_regenerate_id(true);$_SESSION['web_nik']=$nik;$_SESSION['web_role']=$record['role']??web_auth_role($nik);$_SESSION['web_must_change_password']=(bool)($record['must_change_password']??false);
    return ['ok'=>true,'user'=>web_auth_current_user()];
}
function web_auth_current_user(): ?array {
    web_auth_start();$nik=trim((string)($_SESSION['web_nik']??''));$tech=$nik!==''?technician_by_nik($nik):null;if(!$tech)return null;
    return ['nik'=>$nik,'name'=>(string)($tech['name']??$nik),'role'=>strtoupper((string)($_SESSION['web_role']??web_auth_role($nik))),'telegram_id'=>(int)($tech['telegram_id']??0),'sto'=>strtoupper((string)($tech['sto']??'INJOKO')),'must_change_password'=>(bool)($_SESSION['web_must_change_password']??false)];
}
function web_auth_hsa(): ?array { $u=web_auth_current_user();return $u&&$u['role']==='HSA'?$u:null; }
function web_auth_require_user(): array {$u=web_auth_current_user();if(!$u)throw new RuntimeException('WEB_AUTH_REQUIRED');return $u;}
function web_auth_require_hsa(): array {$u=web_auth_require_user();if($u['role']!=='HSA')throw new RuntimeException('WEB_AUTH_FORBIDDEN');return $u;}
function web_auth_change_password(array $payload): array {
    $u=web_auth_require_user();$new=(string)($payload['new_password']??$payload['password']??'');$confirm=(string)($payload['confirm_password']??'');
    if(strlen($new)<6)return ['ok'=>false,'error'=>'weak_password','message'=>'Password minimal 6 karakter.'];if($confirm!==''&&!hash_equals($new,$confirm))return ['ok'=>false,'error'=>'password_mismatch','message'=>'Konfirmasi password tidak sama.'];
    $users=web_auth_load_users();$users[$u['nik']]=['password_hash'=>password_hash($new,PASSWORD_DEFAULT),'role'=>$u['role'],'must_change_password'=>false];if(!web_auth_save_users($users))return ['ok'=>false,'error'=>'write_failed','message'=>'Password gagal disimpan.'];$_SESSION['web_must_change_password']=false;return ['ok'=>true,'message'=>'Password berhasil diganti.'];
}
function web_auth_logout(): array {web_auth_start();$_SESSION=[];session_destroy();return ['ok'=>true];}
