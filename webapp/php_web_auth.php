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

function web_auth_password_hash(): string {
    return trim((string)(getenv('WEB_HSA_PASSWORD_HASH') ?: ''));
}

function web_auth_hsa(): ?array {
    web_auth_start();
    $nik=trim((string)($_SESSION['hsa_nik'] ?? ''));
    if ($nik !== '86240021') return null;
    $tech=technician_by_nik($nik);
    if (!$tech) {
        return [
            'nik'=>$nik,
            'name'=>'HSA',
            'role'=>'HSA',
            'telegram_id'=>(int)($_SESSION['hsa_telegram_id'] ?? 0),
            'sto'=>strtoupper(trim((string)($_SESSION['hsa_sto'] ?? ''))),
        ];
    }
    return [
        'nik'=>$nik,
        'name'=>(string)($tech['name'] ?? 'HSA'),
        'role'=>'HSA',
        'telegram_id'=>(int)($tech['telegram_id'] ?? 0),
        'sto'=>strtoupper(trim((string)($tech['sto'] ?? ''))),
    ];
}

function web_auth_login(array $payload): array {
    web_auth_start();
    $nik=preg_replace('/\D/','',(string)($payload['nik'] ?? '')) ?: '';
    $password=(string)($payload['password'] ?? '');
    if ($nik !== '86240021' || $password === '') return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    $hash=web_auth_password_hash();
    if ($hash === '') return ['ok'=>false,'error'=>'auth_not_configured','message'=>'Login website belum dikonfigurasi di server.'];
    if (!password_verify($password,$hash)) return ['ok'=>false,'error'=>'invalid_credentials','message'=>'NIK atau password salah.'];
    $tech=technician_by_nik($nik);
    if (!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'NIK HSA belum terdaftar di Master Teknisi.'];
    session_regenerate_id(true);
    $_SESSION['hsa_nik']=$nik;
    $_SESSION['hsa_telegram_id']=(int)($tech['telegram_id'] ?? 0);
    $_SESSION['hsa_sto']=strtoupper(trim((string)($tech['sto'] ?? '')));
    return ['ok'=>true,'user'=>web_auth_hsa()];
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
