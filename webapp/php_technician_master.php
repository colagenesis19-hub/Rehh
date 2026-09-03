<?php

declare(strict_types=1);

function technician_master_columns(string $table): array {
    if (!table_exists($table)) return [];
    try { return array_map(fn($r)=>(string)$r['name'], db()->query("PRAGMA table_info($table)")->fetchAll()); }
    catch (Throwable) { return []; }
}

function technician_master_clean_name(mixed $value): string {
    $x = strtoupper(trim((string)$value));
    $x = preg_replace('/^(?:NAME|NAMA)?\s*-?\s*\|\s*/i', '', $x) ?: $x;
    $x = preg_replace('/^(?:NAME|NAMA)\s*[-:=]\s*/i', '', $x) ?: $x;
    $x = preg_replace('/[^A-Z0-9]+/', ' ', $x) ?: $x;
    return trim(preg_replace('/\s+/', ' ', $x) ?: '');
}

function technician_master_username(mixed $value): string { return ltrim(trim((string)$value), '@'); }

function technician_admin_ids(): array {
    $out=[];
    foreach(explode(',',(string)(getenv('ADMIN_IDS') ?: '')) as $id){$id=trim($id);if(ctype_digit($id))$out[]=(int)$id;}
    return array_values(array_unique($out));
}

function technician_privileged_manager(int $telegramId, ?array $viewer=null): bool {
    if(in_array($telegramId,technician_admin_ids(),true)) return true;
    $viewer=$viewer ?: technician_by_telegram($telegramId);
    $nik=trim((string)($viewer['nik']??''));
    return in_array($nik,['91260038','94250015'],true);
}

function ensure_technician_master_schema(): void {
    db()->exec("CREATE TABLE IF NOT EXISTS technician_master (
        nik TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, telegram_id INTEGER,
        username TEXT NOT NULL DEFAULT '', sto TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )");
    db()->exec("CREATE UNIQUE INDEX IF NOT EXISTS idx_technician_master_telegram ON technician_master(telegram_id) WHERE telegram_id IS NOT NULL");
    db()->exec("CREATE TABLE IF NOT EXISTS technician_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nik TEXT NOT NULL, alias TEXT NOT NULL,
        alias_key TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
        UNIQUE(nik, alias_key)
    )");
    db()->exec("CREATE INDEX IF NOT EXISTS idx_technician_alias_key ON technician_aliases(alias_key)");
    if (!table_exists('technicians')) return;
    $rows=db()->query("SELECT telegram_id,nik,name,sto FROM technicians WHERE TRIM(COALESCE(nik,''))<>''")->fetchAll();
    $insert=db()->prepare("INSERT OR IGNORE INTO technician_master(nik,canonical_name,telegram_id,username,sto,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now'))");
    $fill=db()->prepare("UPDATE technician_master SET telegram_id=COALESCE(telegram_id,?), sto=CASE WHEN TRIM(sto)='' THEN ? ELSE sto END, updated_at=datetime('now') WHERE nik=?");
    $alias=db()->prepare("INSERT OR IGNORE INTO technician_aliases(nik,alias,alias_key,source,created_at) VALUES(?,?,?,?,datetime('now'))");
    foreach($rows as $row){
        $nik=preg_replace('/\D/','',(string)($row['nik']??''))?:'';$name=technician_master_clean_name($row['name']??'');
        if($nik===''||$name==='')continue;$username='';
        if(table_exists('technician_usernames')){try{$u=db()->prepare('SELECT username FROM technician_usernames WHERE telegram_id=? LIMIT 1');$u->execute([(int)$row['telegram_id']]);$username=technician_master_username($u->fetchColumn()?:'');}catch(Throwable){}}
        $insert->execute([$nik,$name,(int)$row['telegram_id'],$username,strtoupper(trim((string)($row['sto']??'')))]);
        $fill->execute([(int)$row['telegram_id'],strtoupper(trim((string)($row['sto']??''))),$nik]);
        $alias->execute([$nik,$name,$name,'technicians']);
        if($username!=='')db()->prepare("UPDATE technician_master SET username=CASE WHEN TRIM(username)='' THEN ? ELSE username END WHERE nik=?")->execute([$username,$nik]);
    }
}

function technician_master_rows(): array { ensure_technician_master_schema();return db()->query("SELECT nik,canonical_name,telegram_id,username,sto,updated_at FROM technician_master ORDER BY canonical_name,nik")->fetchAll(); }

function technician_master_alias_map(): array {
    ensure_technician_master_schema();$masters=technician_master_rows();$byNik=[];$byName=[];
    foreach($masters as $m){$nik=trim((string)$m['nik']);$m['canonical_name']=technician_master_clean_name($m['canonical_name']);$byNik[$nik]=$m;$key=technician_master_clean_name($m['canonical_name']);if($key!=='')$byName[$key][]=$nik;}
    foreach(db()->query('SELECT nik,alias_key FROM technician_aliases')->fetchAll() as $a){$key=technician_master_clean_name($a['alias_key']??'');$nik=trim((string)$a['nik']);if($key!==''&&isset($byNik[$nik]))$byName[$key][]=$nik;}
    foreach($byName as $k=>$list)$byName[$k]=array_values(array_unique($list));return[$byNik,$byName];
}

function technician_master_resolve(string $nik='',string $name=''): ?array {
    [$byNik,$byName]=technician_master_alias_map();$nik=preg_replace('/\D/','',$nik)?:'';if($nik!==''&&isset($byNik[$nik]))return$byNik[$nik];
    $key=technician_master_clean_name($name);if($key===''||$key==='-')return null;if(isset($byName[$key])&&count($byName[$key])===1)return$byNik[$byName[$key][0]];
    $tokens=array_values(array_filter(explode(' ',$key)));if(count($tokens)<2)return null;$matches=[];
    foreach($byNik as $candidateNik=>$m){$canonical=technician_master_clean_name($m['canonical_name']);if($canonical===$key||str_starts_with($canonical,$key.' ')||str_starts_with($key,$canonical.' '))$matches[]=$candidateNik;}
    $matches=array_values(array_unique($matches));return count($matches)===1?$byNik[$matches[0]]:null;
}

function technician_master_learn_alias(string $nik,string $alias,string $source): void {
    $alias=technician_master_clean_name($alias);if($nik===''||$alias===''||$alias==='-')return;
    db()->prepare("INSERT OR IGNORE INTO technician_aliases(nik,alias,alias_key,source,created_at) VALUES(?,?,?,?,datetime('now'))")->execute([$nik,$alias,$alias,$source]);
}

function technician_master_normalize_table(string $table,string $nikCol,string $nameCol,?string $usernameCol=null,?string $telegramCol=null): int {
    $cols=technician_master_columns($table);if(!$cols||!in_array($nameCol,$cols,true))return 0;$hasNik=in_array($nikCol,$cols,true);$hasUser=$usernameCol&&in_array($usernameCol,$cols,true);$hasTelegram=$telegramCol&&in_array($telegramCol,$cols,true);
    $select=['rowid AS _rowid',$nameCol.' AS _name'];if($hasNik)$select[]=$nikCol.' AS _nik';$rows=db()->query('SELECT '.implode(',',$select).' FROM '.$table)->fetchAll();$changed=0;
    foreach($rows as $row){$oldName=(string)($row['_name']??'');$oldNik=$hasNik?(string)($row['_nik']??''):'';$master=technician_master_resolve($oldNik,$oldName);if(!$master)continue;technician_master_learn_alias((string)$master['nik'],$oldName,$table);$sets=[];$params=[];if($hasNik){$sets[]="$nikCol=?";$params[]=$master['nik'];}$sets[]="$nameCol=?";$params[]=$master['canonical_name'];if($hasUser){$sets[]="$usernameCol=?";$params[]=technician_master_username($master['username']??'');}if($hasTelegram){$sets[]="$telegramCol=?";$params[]=$master['telegram_id']?:null;}$params[]=(int)$row['_rowid'];db()->prepare('UPDATE '.$table.' SET '.implode(',',$sets).' WHERE rowid=?')->execute($params);$changed++;}
    return$changed;
}

function normalize_technician_data(): array {
    ensure_technician_master_schema();$changed=[];
    $changed['dismantle_orders']=technician_master_normalize_table('dismantle_orders','assigned_nik','assigned_name','assigned_username','assigned_telegram_id');
    $changed['jagir_work_orders']=technician_master_normalize_table('jagir_work_orders','assigned_nik','assigned_name','assigned_username','assigned_telegram_id');
    $changed['orders']=technician_master_normalize_table('orders','assigned_nik','assigned_technician');
    $changed['report_group_orders']=technician_master_normalize_table('report_group_orders','technician_nik','technician_name');
    $changed['report_area_orders']=technician_master_normalize_table('report_area_orders','technician_nik','technician_name');
    return['ok'=>true,'changed'=>$changed,'total_changed'=>array_sum($changed)];
}

function technician_master_reassign_nik(string $oldNik,string $newNik,?int $targetTelegramId): void {
    if($oldNik===''||$newNik===''||$oldNik===$newNik)return;
    $targets=[['dismantle_orders','assigned_nik'],['jagir_work_orders','assigned_nik'],['orders','assigned_nik'],['report_group_orders','technician_nik'],['report_area_orders','technician_nik']];
    foreach($targets as [$table,$column]){if(!table_exists($table)||!in_array($column,technician_master_columns($table),true))continue;try{db()->prepare("UPDATE $table SET $column=? WHERE TRIM(COALESCE($column,''))=?")->execute([$newNik,$oldNik]);}catch(Throwable $e){error_log('[miniapp-php] NIK history migration skipped '.$table.': '.$e->getMessage());}}
    if($targetTelegramId&&table_exists('technicians'))db()->prepare('UPDATE technicians SET nik=? WHERE telegram_id=?')->execute([$newNik,$targetTelegramId]);
}

function canonicalize_dashboard_payload(array $payload): array {
    if(!isset($payload['leaderboard'])||!is_array($payload['leaderboard']))return$payload;$merged=[];
    foreach($payload['leaderboard'] as $row){$master=technician_master_resolve((string)($row['nik']??''),(string)($row['name']??''));if($master){$row['nik']=$master['nik'];$row['name']=$master['canonical_name'];if(trim((string)($row['sto']??''))==='')$row['sto']=$master['sto'];$key='NIK:'.$master['nik'];}else{$key=(string)($row['key']??('NAME:'.technician_master_clean_name($row['name']??'')));}if(!isset($merged[$key])){$row['key']=$key;$merged[$key]=$row;}else{$merged[$key]['total']=(int)($merged[$key]['total']??0)+(int)($row['total']??0);}}
    $payload['leaderboard']=array_values($merged);usort($payload['leaderboard'],fn($a,$b)=>(int)($b['total']??0)<=>(int)($a['total']??0));$total=array_sum(array_map(fn($r)=>(int)($r['total']??0),$payload['leaderboard']));$active=count($payload['leaderboard']);$payload['summary']['total_close']=$total;$payload['summary']['active_technicians']=$active;$payload['summary']['average_close']=$active?round($total/$active,1):0;return$payload;
}

function technician_master_for_viewer(int $telegramId): array {
    ensure_technician_master_schema();$viewer=technician_by_telegram($telegramId);if(!$viewer)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar.'];
    if(!technician_privileged_manager($telegramId,$viewer))return['ok'=>false,'error'=>'forbidden','message'=>'Master Teknisi hanya dapat diakses OSA/HSA atau admin bot.'];
    $items=[];foreach(technician_master_rows() as $m){$st=db()->prepare('SELECT alias FROM technician_aliases WHERE nik=? ORDER BY alias');$st->execute([$m['nik']]);$m['aliases']=array_values(array_unique(array_map(fn($r)=>(string)$r['alias'],$st->fetchAll())));$items[]=$m;}
    return['ok'=>true,'can_manage'=>true,'role'=>in_array($telegramId,technician_admin_ids(),true)?'ADMIN':'SUPERVISOR','items'=>$items,'normalization'=>normalize_technician_data()];
}

function save_technician_master(array $payload): array {
    ensure_technician_master_schema();$rawTelegram=trim((string)($payload['telegram_id']??''));if(!ctype_digit($rawTelegram))return['ok'=>false,'error'=>'invalid_request'];$viewerId=(int)$rawTelegram;$viewer=technician_by_telegram($viewerId);
    if(!$viewer||!technician_privileged_manager($viewerId,$viewer))return['ok'=>false,'error'=>'forbidden','message'=>'Hanya OSA/HSA atau admin bot yang dapat mengubah Master Teknisi.'];
    $nik=preg_replace('/\D/','',(string)($payload['nik']??''))?:'';$originalNik=preg_replace('/\D/','',(string)($payload['original_nik']??$nik))?:'';$name=technician_master_clean_name($payload['canonical_name']??'');
    if($nik===''||$name==='')return['ok'=>false,'error'=>'invalid_data','message'=>'NIK dan nama resmi wajib diisi.'];
    $username=technician_master_username($payload['username']??'');$sto=strtoupper(trim((string)($payload['sto']??'')));
    $old=db()->prepare('SELECT telegram_id FROM technician_master WHERE nik=? LIMIT 1');$old->execute([$originalNik]);$targetTelegram=$old->fetchColumn();$targetTelegram=$targetTelegram!==false?(int)$targetTelegram:null;
    if($originalNik!==$nik){$dupe=db()->prepare('SELECT telegram_id FROM technician_master WHERE nik=? LIMIT 1');$dupe->execute([$nik]);$dupeId=$dupe->fetchColumn();if($dupeId!==false&&($targetTelegram===null||(int)$dupeId!==$targetTelegram))return['ok'=>false,'error'=>'nik_in_use','message'=>'NIK baru sudah dipakai teknisi lain.'];}
    db()->beginTransaction();
    try{
        if($originalNik!==$nik){technician_master_reassign_nik($originalNik,$nik,$targetTelegram);db()->prepare("INSERT OR IGNORE INTO technician_aliases(nik,alias,alias_key,source,created_at) SELECT ?,alias,alias_key,source,created_at FROM technician_aliases WHERE nik=?")->execute([$nik,$originalNik]);db()->prepare('DELETE FROM technician_aliases WHERE nik=?')->execute([$originalNik]);db()->prepare('DELETE FROM technician_master WHERE nik=?')->execute([$originalNik]);}
        db()->prepare("INSERT INTO technician_master(nik,canonical_name,telegram_id,username,sto,created_at,updated_at) VALUES(?,?,?,?,?,datetime('now'),datetime('now')) ON CONFLICT(nik) DO UPDATE SET canonical_name=excluded.canonical_name,telegram_id=COALESCE(excluded.telegram_id,technician_master.telegram_id),username=excluded.username,sto=excluded.sto,updated_at=datetime('now')")->execute([$nik,$name,$targetTelegram,$username,$sto]);
        technician_master_learn_alias($nik,$name,'master');foreach((array)($payload['aliases']??[]) as $alias)technician_master_learn_alias($nik,(string)$alias,'manual');db()->commit();
    }catch(Throwable $e){if(db()->inTransaction())db()->rollBack();throw$e;}
    $normalization=normalize_technician_data();return['ok'=>true,'nik'=>$nik,'previous_nik'=>$originalNik,'normalization'=>$normalization];
}
