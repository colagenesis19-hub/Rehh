<?php

declare(strict_types=1);

/** Read-only master listing for the Mini App hot path. Never normalizes legacy tables. */
function technician_master_for_viewer_fast(int $telegramId): array {
    $viewer=technician_by_telegram($telegramId);
    if(!$viewer)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar.'];
    if(!technician_privileged_manager($telegramId,$viewer))return['ok'=>false,'error'=>'forbidden','message'=>'Master Teknisi hanya dapat diakses OSA/HSA atau admin bot.'];

    $items=[];
    try {
        if(table_exists('technician_master')) {
            $rows=db()->query("SELECT nik,canonical_name,telegram_id,username,sto,updated_at FROM technician_master ORDER BY canonical_name,nik")->fetchAll();
            $aliases=[];
            if(table_exists('technician_aliases')) {
                foreach(db()->query('SELECT nik,alias FROM technician_aliases ORDER BY alias')->fetchAll() as $a){
                    $aliases[(string)$a['nik']][]=(string)$a['alias'];
                }
            }
            foreach($rows as $m){$m['aliases']=array_values(array_unique($aliases[(string)$m['nik']]??[]));$items[]=$m;}
        }
    } catch(Throwable $e) {
        error_log('[miniapp-php] fast master read fallback: '.$e->getMessage());
        $items=[];
    }

    if(!$items && table_exists('technicians')) {
        $rows=db()->query("SELECT telegram_id,nik,name,sto FROM technicians WHERE TRIM(COALESCE(nik,''))<>'' ORDER BY name")->fetchAll();
        foreach($rows as $r){
            $items[]=['nik'=>(string)$r['nik'],'canonical_name'=>(string)$r['name'],'telegram_id'=>(int)$r['telegram_id'],'username'=>'','sto'=>(string)$r['sto'],'updated_at'=>null,'aliases'=>[]];
        }
    }
    return['ok'=>true,'can_manage'=>true,'role'=>in_array($telegramId,technician_admin_ids(),true)?'ADMIN':'SUPERVISOR','items'=>$items,'normalization'=>['total_changed'=>0],'read_only_load'=>true];
}
