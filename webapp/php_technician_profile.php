<?php

declare(strict_types=1);

function technician_profile_get(int $telegramId): array {
    $tech=technician_by_telegram($telegramId);
    if(!$tech)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $username='';
    if(table_exists('technician_usernames')){try{$st=db()->prepare('SELECT username FROM technician_usernames WHERE telegram_id=? LIMIT 1');$st->execute([$telegramId]);$username=ltrim(trim((string)($st->fetchColumn()?:'')),'@');}catch(Throwable){}}
    $nik=trim((string)($tech['nik']??''));$privileged=technician_privileged_manager($telegramId,$tech);
    return['ok'=>true,'profile'=>[
        'telegram_id'=>$telegramId,'nik'=>$nik,'name'=>trim((string)($tech['name']??'')),
        'sto'=>strtoupper(trim((string)($tech['sto']??''))),'username'=>$username,
        'can_edit_nik'=>$nik===''||$privileged,'nik_empty'=>$nik==='','can_manage_master'=>$privileged,
        'manager_role'=>$privileged?(in_array($telegramId,technician_admin_ids(),true)?'ADMIN':'SUPERVISOR'):'TECHNICIAN',
    ]];
}

function technician_profile_save(array $payload): array {
    $raw=trim((string)($payload['telegram_id']??''));if(!ctype_digit($raw))return['ok'=>false,'error'=>'invalid_request','message'=>'Telegram ID tidak valid.'];
    $telegramId=(int)$raw;$tech=technician_by_telegram($telegramId);if(!$tech)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $currentNik=preg_replace('/\D/','',(string)($tech['nik']??''))?:'';$requestedNik=preg_replace('/\D/','',(string)($payload['nik']??$currentNik))?:'';$privileged=technician_privileged_manager($telegramId,$tech);
    $name=trim(preg_replace('/\s+/',' ',(string)($payload['name']??''))?:'');$sto=strtoupper(trim((string)($payload['sto']??'')));$username=ltrim(trim((string)($payload['username']??'')),'@');$nameLen=strlen($name);
    if($name===''||$nameLen<3||$nameLen>80)return['ok'=>false,'error'=>'invalid_name','message'=>'Nama harus 3-80 karakter.'];
    if($sto!==''&&!preg_match('/^[A-Z0-9]{2,8}$/',$sto))return['ok'=>false,'error'=>'invalid_sto','message'=>'Format STO tidak valid.'];
    if($username!==''&&!preg_match('/^[A-Za-z0-9_]{5,32}$/',$username))return['ok'=>false,'error'=>'invalid_username','message'=>'Username Telegram tidak valid.'];
    if($requestedNik!==''&&!preg_match('/^\d{5,12}$/',$requestedNik))return['ok'=>false,'error'=>'invalid_nik','message'=>'Format NIK tidak valid.'];
    if($currentNik!==''&&$requestedNik!==$currentNik&&!$privileged)return['ok'=>false,'error'=>'nik_locked','message'=>'NIK sudah terkunci. Koreksi hanya dapat dilakukan OSA/HSA atau admin bot.'];
    if($currentNik===''&&$requestedNik==='')return['ok'=>false,'error'=>'nik_required','message'=>'NIK belum terhubung. Isi NIK terlebih dahulu.'];
    if($requestedNik!==$currentNik){
        $dupe=db()->prepare('SELECT telegram_id FROM technicians WHERE TRIM(COALESCE(nik,\'\'))=? AND telegram_id<>? LIMIT 1');$dupe->execute([$requestedNik,$telegramId]);
        if($dupe->fetchColumn()!==false)return['ok'=>false,'error'=>'nik_in_use','message'=>'NIK tersebut sudah terhubung ke akun teknisi lain.'];
        if(table_exists('technician_master')){$d=db()->prepare('SELECT telegram_id FROM technician_master WHERE nik=? LIMIT 1');$d->execute([$requestedNik]);$other=$d->fetchColumn();if($other!==false&&(int)$other!==$telegramId)return['ok'=>false,'error'=>'nik_in_use','message'=>'NIK tersebut sudah ada di Master Teknisi.'];}
    }
    db()->beginTransaction();
    try{
        db()->prepare('UPDATE technicians SET nik=?,name=?,sto=? WHERE telegram_id=?')->execute([$requestedNik,$name,$sto,$telegramId]);
        if(table_exists('technician_usernames')){$cols=technician_master_columns('technician_usernames');if(in_array('telegram_id',$cols,true)&&in_array('username',$cols,true)){try{db()->prepare("INSERT INTO technician_usernames(telegram_id,username) VALUES(?,?) ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username")->execute([$telegramId,$username]);}catch(Throwable){$u=db()->prepare('UPDATE technician_usernames SET username=? WHERE telegram_id=?');$u->execute([$username,$telegramId]);if($u->rowCount()===0){try{db()->prepare('INSERT INTO technician_usernames(telegram_id,username) VALUES(?,?)')->execute([$telegramId,$username]);}catch(Throwable){}}}}}
        db()->commit();
    }catch(Throwable $e){if(db()->inTransaction())db()->rollBack();throw$e;}
    try{
        if(table_exists('technician_master')){
            if($currentNik!==''&&$requestedNik!==$currentNik&&$privileged)technician_master_reassign_nik($currentNik,$requestedNik,$telegramId);
            db()->prepare("INSERT INTO technician_master(nik,canonical_name,telegram_id,username,sto,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now')) ON CONFLICT(nik) DO UPDATE SET canonical_name=excluded.canonical_name,telegram_id=excluded.telegram_id,username=excluded.username,sto=excluded.sto,updated_at=datetime('now')")->execute([$requestedNik,technician_master_clean_name($name),$telegramId,$username,$sto]);
            technician_master_learn_alias($requestedNik,$name,'profile');
        }
    }catch(Throwable $e){error_log('[miniapp-php] profile master sync skipped: '.$e->getMessage());}
    return technician_profile_get($telegramId)+['saved'=>true,'nik_linked_now'=>$currentNik===''&&$requestedNik!=='','nik_corrected'=>$currentNik!==''&&$requestedNik!==$currentNik];
}
