<?php

declare(strict_types=1);

function web_auth_start(): void {
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_name('INJOKO_WEB');
        session_set_cookie_params([
            'lifetime'=>0,
            'path'=>'/',
            'secure'=>true,
            'httponly'=>true,
            'samesite'=>'Lax',
        ]);
        session_start();
    }
}

function web_auth_file(): string {
    return dirname(__DIR__) . '/database/web_auth.json';
}

function web_auth_password_hash(): string {
    $file=web_auth_file();
    if (is_file($file)) {
        $data=json_decode((string)@file_get_contents($file),true);
        if (is_array($data) && !empty($data['password_hash'])) return trim((string)$data['password_hash']);
    }
    // First-login password is always the HSA NIK.
    return password_hash('86240021', PASSWORD_DEFAULT);
}

function web_auth_hsa(): ?array {
    web_auth_start();
    $nik=trim((string)($_SESSION['hsa_nik'] ?? ''));
    if ($nik !== '86240021') return null;
    $tech=technician_by_nik($nik);
    return [
        'nik'=>$nik,
        'name'=>(string)($tech['name'] ?? 'HSA'),
        'role'=>'HSA',
        'telegram_id'=>(int)($tech['telegram_id'] ?? 0),
        'sto'=>strtoupper(trim((string)($tech['sto'] ?? 'INJOKO'))),
    ];
}

function web_auth_login(array $payload): array {
    web_auth_start();
    $nik=preg_replace('/\D/','',(string)($payload['nik'] ?? '')) ?: '';
    $password=(string)($payload['password'] ?? '');
    if ($nik !== '86240021' || $password === '') return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    if (!password_verify($password,web_auth_password_hash())) return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    session_regenerate_id(true);
    $tech=technician_by_nik($nik);
    $_SESSION['hsa_nik']=$nik;
    $_SESSION['hsa_telegram_id']=(int)($tech['telegram_id'] ?? 0);
    $_SESSION['hsa_sto']=strtoupper(trim((string)($tech['sto'] ?? 'INJOKO')));
    return ['ok'=>true,'user'=>web_auth_hsa()];
}

function web_auth_change_password(array $payload): array {
    $user=web_auth_require_hsa();
    $new=(string)($payload['new_password'] ?? '');
    $confirm=(string)($payload['confirm_password'] ?? '');
    if (strlen($new) < 6) return ['ok'=>false,'error'=>'weak_password','message'=>'Password minimal 6 karakter.'];
    if ($new !== $confirm) return ['ok'=>false,'error'=>'password_mismatch','message'=>'Konfirmasi password tidak sama.'];
    $file=web_auth_file();
    $dir=dirname($file);
    if (!is_dir($dir) && !@mkdir($dir,0775,true) && !is_dir($dir)) return ['ok'=>false,'error'=>'write_failed','message'=>'Folder penyimpanan login tidak dapat dibuat.'];
    $data=['nik'=>$user['nik'],'password_hash'=>password_hash($new,PASSWORD_DEFAULT),'updated_at'=>date('c')];
    $tmp=$file.'.tmp';
    if (@file_put_contents($tmp,json_encode($data,JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES|JSON_PRETTY_PRINT),LOCK_EX)===false || !@rename($tmp,$file)) {
        @unlink($tmp);
        return ['ok'=>false,'error'=>'write_failed','message'=>'Password gagal disimpan di server.'];
    }
    @chmod($file,0600);
    return ['ok'=>true,'message'=>'Password berhasil diganti.'];
}

function web_auth_logout(): array {
    web_auth_start();
    $_SESSION=[];
    if (ini_get('session.use_cookies')) {
        $params=session_get_cookie_params();
        setcookie(session_name(),'',time()-42000,$params['path'],$params['domain'] ?? '',(bool)$params['secure'],(bool)$params['httponly']);
    }
    session_destroy();
    return ['ok'=>true];
}

function web_auth_require_hsa(): array {
    $user=web_auth_hsa();
    if (!$user) throw new RuntimeException('WEB_AUTH_REQUIRED');
    return $user;
}

function technician_by_nik(string $nik): ?array {
    $nik=trim($nik);
    if ($nik==='') return null;
    if (!table_exists('technicians')) return null;
    $st=db()->prepare('SELECT telegram_id,nik,name,sto FROM technicians WHERE TRIM(nik)=? LIMIT 1');
    $st->execute([$nik]);
    $row=$st->fetch();
    return $row ?: null;
}
