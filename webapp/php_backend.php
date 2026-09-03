<?php

declare(strict_types=1);

date_default_timezone_set(getenv('TZ') ?: 'Asia/Jakarta');

const DEFAULT_SHEET_ID = '18PPhNfdfIZtoAJoWvX9IqEAWysZ48swXgWKLFZIpM9Y';
const DEFAULT_SHEET_GID = '0';
const CLOSED_STATUSES = ['CLOSE','CLOSED','DONE','SELESAI','COMPLETED'];
const UPDATE_STATUSES = ['UPDATE','UPDATED','PROGRESS','ON PROGRESS','PENDING'];
const MONTHS_ID = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
const DAYS_ID = ['Sen','Sel','Rab','Kam','Jum','Sab','Min'];

function db_path(): string {
    return getenv('DATABASE_PATH') ?: '/app/database/bot.sqlite3';
}

function db(): PDO {
    static $pdo = null;
    if ($pdo instanceof PDO) return $pdo;
    $pdo = new PDO('sqlite:' . db_path(), null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA busy_timeout=5000');
    $pdo->exec('PRAGMA journal_mode=WAL');
    return $pdo;
}

function table_exists(string $name): bool {
    $st = db()->prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?");
    $st->execute([$name]);
    return (bool)$st->fetchColumn();
}

function clean(?string $v): string {
    $v = trim((string)$v);
    return in_array(strtoupper($v), ['', '-', 'N/A', 'NA', 'NONE', '#N/A'], true) ? '' : $v;
}

function norm(mixed $v): string {
    return preg_replace('/\s+/', ' ', strtoupper(trim((string)$v))) ?: '';
}

function norm_key(mixed $v): string {
    return preg_replace('/[^A-Z0-9]/', '', norm($v)) ?: '';
}

function norm_name(mixed $v): string {
    $x = norm($v);
    $x = preg_replace('/^(?:NAME|NAMA)\s*[-:=]\s*/', '', $x) ?: $x;
    $x = preg_replace('/[^A-Z0-9]+/', ' ', $x) ?: $x;
    return trim(preg_replace('/\s+/', ' ', $x) ?: '');
}

function normalize_ticket(mixed $v): string {
    $x = norm($v);
    return in_array($x, ['', '-', 'MANUAL', 'N/A', 'NA', 'NONE'], true) ? '' : $x;
}

function period_bounds(DateTimeImmutable $day): array {
    $weekday = (int)$day->format('N') - 1; // Mon=0
    $daysSinceFriday = ($weekday - 4 + 7) % 7;
    $start = $day->modify("-$daysSinceFriday days");
    return [$start, $start->modify('+6 days')];
}

function date_label(DateTimeImmutable $d): string {
    return $d->format('j') . ' ' . MONTHS_ID[(int)$d->format('n') - 1] . ' ' . $d->format('Y');
}

function get_settings(): array {
    $settings = ['google_sheet_id' => DEFAULT_SHEET_ID, 'google_sheet_gid' => DEFAULT_SHEET_GID];
    try {
        if (!table_exists('bot_settings')) return $settings;
        foreach (db()->query('SELECT key,value FROM bot_settings')->fetchAll() as $row) {
            if (array_key_exists($row['key'], $settings) && trim((string)$row['value']) !== '') {
                $settings[$row['key']] = trim((string)$row['value']);
            }
        }
    } catch (Throwable) {}
    return $settings;
}

function sheet_csv_url(): string {
    $s = get_settings();
    return 'https://docs.google.com/spreadsheets/d/' . rawurlencode($s['google_sheet_id']) . '/export?format=csv&gid=' . rawurlencode($s['google_sheet_gid']);
}

function header_aliases(): array {
    return [
        'ticket' => ['TIKET','TICKET','TICKET ID','TIKET ID','INC','NO TIKET','NO. TIKET','NOMOR TIKET'],
        'insera_ticket' => ['INSERA TODAY','TIKET INSERA','TICKET INSERA','INSERA','INSERA TICKET'],
        'service_number' => ['NO INET','NO INTERNET','NO SERVICE','SERVICE NUMBER','INTERNET NUMBER','INET'],
        'status' => ['STATUS','RESULT','HASIL','STATUS ORDER','STATUS HASIL'],
        'voip_number' => ['NO VOIP','VOIP','VOICE','NO VOICE'],
        'customer_name' => ['NAMA PELANGGAN','CUSTOMER NAME','NAMA CUSTOMER','NAMA'],
        'address' => ['ALAMAT','ADDRESS','ALAMAT PELANGGAN'],
        'customer_phone' => ['CP','NO HP','NO. HP','NOMOR HP','CP / NO HP','CONTACT PERSON','PHONE'],
        'package' => ['PAKET','KECEPATAN','SPEED','SPEED PAKET','PAKET INTERNET','BANDWIDTH','SPEED BY TACPRO'],
        'onu_rx' => ['ONU RX','ONU_RX','RX ONU','ONU RX POWER','RX POWER ONU'],
        'rca' => ['RCA','ROOT CAUSE','ROOT CAUSE ANALYSIS'],
        'old_sn' => ['SN ONT LAMA','SN ONT OLD','SN LAMA','OLD SN','SN OLD','SERIAL NUMBER LAMA'],
        'new_sn' => ['SN ONT NEW','SN ONT BARU','SN NEW','NEW SN','SN BARU','SERIAL NUMBER BARU'],
        'ont_type' => ['TYPE ONT','TIPE ONT','MODEL ONT','MODEL ONT BARU','TYPE ONT BARU','TIPE ONT BARU'],
        'sto' => ['STO','KODE STO'],
        'valins_id' => ['VALINS ID','ID VALINS','VALINS'],
        'config_description' => ['KETERANGAN CONFIG','KETERANGAN KONFIG','DESKRIPSI CONFIG','KET CONFIG'],
        'report_description' => ['KETERANGAN REPORT/STO','KETERANGAN REPORT','KETERANGAN STO','KET REPORT/STO','KET REPORT'],
        'assigned_technician' => ['NAMA PETUGAS','PETUGAS','TEKNISI','NAMA TEKNISI','ASSIGNED TECHNICIAN'],
    ];
}

function fetch_sheet(bool $force=false): array {
    $cache = '/tmp/kerja-bot-sheet-cache.json';
    if (!$force && is_file($cache) && time() - filemtime($cache) < 30) {
        $decoded = json_decode((string)file_get_contents($cache), true);
        if (is_array($decoded)) return $decoded;
    }
    $ctx = stream_context_create(['http' => ['timeout' => 20, 'header' => "User-Agent: Kerja-Bot-PHP/1.0\r\n"]]);
    $raw = @file_get_contents(sheet_csv_url(), false, $ctx);
    if ($raw === false || trim($raw) === '') throw new RuntimeException('Google Sheets tidak dapat dibaca.');
    $fp = fopen('php://temp', 'r+');
    fwrite($fp, preg_replace('/^\xEF\xBB\xBF/', '', $raw)); rewind($fp);
    $rows=[]; while (($r=fgetcsv($fp))!==false) $rows[]=$r; fclose($fp);
    $aliases = header_aliases(); $headerIndex=-1; $cols=[];
    foreach (array_slice($rows,0,20,true) as $i=>$row) {
        $candidate=[];
        foreach ($aliases as $key=>$opts) {
            $candidate[$key]=null;
            foreach ($row as $j=>$h) if (in_array(norm($h), array_map('norm',$opts), true)) { $candidate[$key]=$j; break; }
        }
        if ($candidate['service_number']!==null && $candidate['status']!==null) { $headerIndex=$i; $cols=$candidate; break; }
    }
    if ($headerIndex<0) throw new RuntimeException('Kolom INET/STATUS tidak ditemukan di Google Sheet.');
    $out=[];
    for ($i=$headerIndex+1;$i<count($rows);$i++) {
        $row=$rows[$i]; $v=[];
        foreach ($cols as $k=>$c) $v[$k]=($c!==null && array_key_exists($c,$row))?trim((string)$row[$c]):'';
        $service=trim($v['service_number']); $ticket=normalize_ticket($v['insera_ticket']) ?: normalize_ticket($v['ticket']);
        if ($service==='' && $ticket==='') continue;
        $item=[
            'status'=>norm($v['status']),'ticket_id'=>$ticket,'service_number'=>$service,
            'voip_number'=>$v['voip_number'],'customer_name'=>$v['customer_name'],'address'=>$v['address'],
            'customer_phone'=>$v['customer_phone'],'package'=>$v['package'],'onu_rx'=>$v['onu_rx'],'rca'=>$v['rca'],
            'old_sn'=>norm($v['old_sn']),'new_sn'=>norm($v['new_sn']),'ont_type'=>norm($v['ont_type']),
            'sto'=>norm($v['sto']),'valins_id'=>$v['valins_id'],'config_description'=>$v['config_description'],
            'report_description'=>$v['report_description'],'assigned_technician'=>$v['assigned_technician'],
        ];
        $key=norm_key($service ?: $ticket); if ($key!=='') $out[$key]=$item;
    }
    @file_put_contents($cache, json_encode($out, JSON_UNESCAPED_UNICODE));
    return $out;
}

function sheet_bucket(array $r): string {
    $s=norm($r['status']??'');
    if (in_array($s,CLOSED_STATUSES,true)) return 'close';
    if (in_array($s,UPDATE_STATUSES,true) || str_contains($s,'UPDATE') || str_contains($s,'PROGRESS')) return 'update';
    return 'open';
}

function normalize_address(string $address): string {
    $t=preg_replace('/[^A-Z0-9 ]+/', ' ', norm($address)) ?: '';
    return trim(preg_replace('/\s+/', ' ', $t) ?: '');
}

function classify_area(string $address): string {
    $text=normalize_address($address); if ($text==='') return 'LAINNYA';
    $aliases=['KERTAJAYA'=>['KERTAJAYA INDAH TIMUR','KERTAJAYA INDAH','KERTAJAYA'],'MULYOREJO'=>['MULYOREJO'],'KEPUTIH'=>['KEPUTIH']];
    foreach ($aliases as $area=>$arr) foreach($arr as $a) if (str_contains($text,$a)) return $area;
    $prefix=['JL','JLN','JALAN','GG','GANG','PERUM','PERUMAHAN','KOMP','KOMPLEK','KOMPLEKS','KP','KAMPUNG'];
    foreach (explode(' ',$text) as $tok) {
        if (in_array($tok,$prefix,true)||ctype_digit($tok)||strlen($tok)<4||preg_match('/^\d+[A-Z]?$/',$tok)) continue;
        return $tok;
    }
    return 'LAINNYA';
}

function technician_by_telegram(int $id): ?array {
    try { $st=db()->prepare('SELECT id,telegram_id,nik,name,sto FROM technicians WHERE telegram_id=?'); $st->execute([$id]); $r=$st->fetch(); return $r?:null; }
    catch(Throwable){ return null; }
}

function wo_payload(array $r): array {
    return [
        'customer_name'=>clean($r['customer_name']??'') ?: '-', 'ticket_id'=>clean($r['ticket_id']??'') ?: 'MANUAL',
        'service_number'=>clean($r['service_number']??'') ?: '-', 'customer_phone'=>clean($r['customer_phone']??'') ?: '-',
        'package'=>clean($r['package']??'') ?: '-', 'onu_rx'=>clean($r['onu_rx']??'') ?: '-', 'rca'=>clean($r['description']??'') ?: '-',
        'address'=>clean($r['address']??'') ?: '-', 'voip_number'=>'','old_sn'=>'','new_sn'=>'',
        'ont_type'=>clean($r['order_type']??''),'sto'=>'JGR','valins_id'=>'','config_description'=>'',
        'report_description'=>clean($r['description']??''),'result'=>'',
        'assigned_technician'=>clean($r['assigned_name']??'') ?: (($r['assigned_username']??'') ? '@'.$r['assigned_username'] : '-'),
        'assigned_username'=>clean($r['assigned_username']??''),'odp_name'=>clean($r['odp_name']??''),'area'=>'JAGIR','source'=>'WORK ORDER JAGIR'
    ];
}

function my_jagir_orders(int $telegramId,array $tech): array {
    if (!table_exists('jagir_work_orders')) return [];
    $username='';
    if (table_exists('technician_usernames')) { $st=db()->prepare('SELECT username FROM technician_usernames WHERE telegram_id=?');$st->execute([$telegramId]);$username=strtolower(trim((string)($st->fetchColumn()?:''))); }
    $nik=trim((string)($tech['nik']??'')); $name=norm_name($tech['name']??'');
    $st=db()->prepare("SELECT * FROM jagir_work_orders WHERE UPPER(TRIM(status))='OPEN' AND (assigned_telegram_id=? OR (?<>'' AND TRIM(assigned_nik)=?) OR (?<>'' AND UPPER(TRIM(assigned_name))=?) OR (?<>'' AND LOWER(TRIM(assigned_username))=?)) ORDER BY address,service_number");
    $st->execute([$telegramId,$nik,$nik,$name,$name,$username,$username]);
    return array_map('wo_payload',$st->fetchAll());
}

function order_payload(array $r,string $source='ORDER SHEET'): array {
    $pkg=clean($r['package']??''); if ($pkg!=='' && preg_match('/^\d+(?:[.,]\d+)?$/',$pkg)) $pkg.=' Mbps';
    return [
        'customer_name'=>clean($r['customer_name']??'')?:'-','ticket_id'=>normalize_ticket($r['ticket_id']??'')?:'MANUAL',
        'service_number'=>clean($r['service_number']??'')?:'-','customer_phone'=>clean($r['customer_phone']??'')?:'-',
        'package'=>$pkg?:'-','onu_rx'=>clean($r['onu_rx']??'')?:'-','rca'=>clean($r['rca']??'')?:'-','address'=>clean($r['address']??'')?:'-',
        'voip_number'=>clean($r['voip_number']??''),'old_sn'=>clean($r['old_sn']??''),'new_sn'=>clean($r['new_sn']??''),'ont_type'=>clean($r['ont_type']??''),
        'sto'=>$source==='ORDER SHEET'?'MYR':clean($r['sto']??''),'valins_id'=>clean($r['valins_id']??''),'config_description'=>clean($r['config_description']??''),
        'report_description'=>clean($r['report_description']??''),'result'=>'','assigned_technician'=>clean($r['assigned_technician']??'')?:'-',
        'area'=>classify_area((string)($r['address']??'')),'source'=>$source
    ];
}

function load_my_open_orders(int $telegramId,bool $force=false): array {
    $tech=technician_by_telegram($telegramId); if(!$tech) return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $refs=fetch_sheet($force); $wanted=norm_name($tech['name']??''); $summary=[];$groups=[];
    foreach($refs as $r){ if(norm_name($r['assigned_technician']??'')!==$wanted)continue; $area=classify_area((string)$r['address']);$bucket=sheet_bucket($r);$summary[$area]??=['open'=>0,'close'=>0,'update'=>0];$summary[$area][$bucket]++;if($bucket==='open')$groups[$area][]=order_payload($r); }
    $areas=[];foreach($groups as $area=>$orders){ usort($orders,fn($a,$b)=>strnatcasecmp($a['address'],$b['address']));$c=$summary[$area];$areas[]=['area'=>$area,'open'=>count($orders),'close'=>$c['close'],'update'=>$c['update'],'orders'=>$orders]; }
    $j=my_jagir_orders($telegramId,$tech); if($j){$areas[]=['area'=>'JAGIR','open'=>count($j),'close'=>0,'update'=>0,'orders'=>$j];}
    usort($areas,fn($a,$b)=>($a['area']==='JAGIR'?1:0)<=>($b['area']==='JAGIR'?1:0) ?: strcmp($a['area'],$b['area']));
    return ['ok'=>true,'technician'=>['telegram_id'=>$telegramId,'nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto']], 'source'=>'ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)','total_open'=>array_sum(array_column($areas,'open')),'active_areas'=>count($areas),'areas'=>$areas];
}

function search_open_orders(int $telegramId,string $query,bool $force=false): array {
    $tech=technician_by_telegram($telegramId);if(!$tech)return ['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];
    $wanted=preg_replace('/\D/','',$query)?:'';if(strlen($wanted)<6)return ['ok'=>false,'error'=>'query_too_short','message'=>'Masukkan minimal 6 digit nomor INET.'];
    $merged=[];foreach(fetch_sheet($force) as $r){if(sheet_bucket($r)!=='open')continue;$s=preg_replace('/\D/','',(string)$r['service_number'])?:'';if(!str_contains($s,$wanted))continue;$o=order_payload($r);$merged[$o['service_number']]=$o;}
    if(table_exists('jagir_work_orders')){$st=db()->prepare("SELECT * FROM jagir_work_orders WHERE UPPER(TRIM(status))='OPEN' AND service_number LIKE ? LIMIT 20");$st->execute(['%'.$wanted.'%']);foreach($st->fetchAll() as $r){$o=wo_payload($r);$merged[$o['service_number']]=$o;}}
    $orders=array_values($merged);usort($orders,fn($a,$b)=>(($a['service_number']===$wanted)?0:1)<=>((($b['service_number']===$wanted)?0:1)) ?: strcmp($a['service_number'],$b['service_number']));$orders=array_slice($orders,0,20);
    return ['ok'=>true,'query'=>$wanted,'count'=>count($orders),'orders'=>$orders,'technician'=>['telegram_id'=>$telegramId,'nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto']],'source'=>'ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)'];
}

function area_condition(string $area): array {
    $area=strtoupper(trim($area));
    if($area==='JGR')return ["EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?)",['JGR']];
    if($area==='MYR')return ["(EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?) OR (NOT EXISTS (SELECT 1 FROM report_area_orders ra0 WHERE ra0.service_number=r.service_number AND ra0.period_start=r.period_start) AND EXISTS (SELECT 1 FROM orders o WHERE o.service_number=r.service_number AND UPPER(TRIM(o.sto))=?)))",['MYR','MYR']];
    return ['1=1',[]];
}

function report_rows(string $where,array $params): array {
    if(!table_exists('report_group_orders'))return[];
    $sql="SELECT r.technician_nik nik,r.technician_name name,r.service_number,r.period_start,r.message_date,UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''),ra.sto_code,o.sto,''))) area_label,UPPER(TRIM(COALESCE(ra.sto_code,o.sto,''))) sto FROM report_group_orders r LEFT JOIN report_area_orders ra ON ra.service_number=r.service_number AND ra.period_start=r.period_start LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1) WHERE $where";
    $st=db()->prepare($sql);$st->execute($params);return $st->fetchAll();
}

function technician_registry(): array {
    if(!table_exists('technicians'))return[];$out=[];foreach(db()->query('SELECT nik,name,sto FROM technicians ORDER BY id')->fetchAll() as $r){$k=norm_name($r['name']);if($k!=='')$out[$k]=$r;}return$out;
}

function group_report_rows(array $rows): array {
    $reg=technician_registry();$g=[];
    foreach($rows as $r){$nk=norm_name($r['name']);$registered=$reg[$nk]??[];$key=$nk!==''?'NAME:'.$nk:'NIK:'.norm_key($r['nik']);$g[$key]??=['key'=>$key,'nik'=>trim((string)($registered['nik']??$r['nik'])),'name'=>trim((string)($registered['name']??$r['name']??'-')),'sto'=>strtoupper(trim((string)($registered['sto']??''))),'services'=>[],'latest'=>'','area_label'=>'','area_sto'=>'','nik_candidates'=>[]];$s=trim((string)$r['service_number']);if($s!=='')$g[$key]['services'][$s]=1;$rawNik=trim((string)$r['nik']);if($rawNik!==''&&!in_array($rawNik,$g[$key]['nik_candidates'],true))$g[$key]['nik_candidates'][]=$rawNik;if((string)$r['message_date']>=$g[$key]['latest']){$g[$key]['latest']=$r['message_date'];$g[$key]['area_label']=$r['area_label'];$g[$key]['area_sto']=$r['sto'];}}
    $out=[];foreach($g as $it){if($it['nik']===''||str_starts_with(strtoupper($it['nik']),'NAME-')||str_starts_with(strtoupper($it['nik']),'TG-'))foreach($it['nik_candidates'] as $c)if(!str_starts_with(strtoupper($c),'NAME-')&&!str_starts_with(strtoupper($c),'TG-')){$it['nik']=$c;break;}$out[]=['key'=>$it['key'],'nik'=>$it['nik'],'name'=>$it['name'],'total'=>count($it['services']),'area_label'=>$it['area_label'],'sto'=>$it['area_sto']?:$it['sto']];}
    usort($out,fn($a,$b)=>$b['total']<=>$a['total'] ?: strcmp(norm_name($a['name']),norm_name($b['name'])));return$out;
}

function load_rca_summary(string $area): array {
    $area=strtoupper(trim($area));$merged=[];
    try{foreach(fetch_sheet(false) as $r){$service=trim((string)$r['service_number']);if($service==='')continue;$sto=strtoupper(trim((string)$r['sto']));if(in_array($area,['MYR','JGR'],true)&&$sto!==''&&$sto!==$area)continue;$rca=norm($r['rca']);if($rca!==''&&!in_array($rca,['-','N/A','NA','NONE','#N/A'],true))$merged[$service]=['rca'=>$rca,'source'=>'SHEET'];}}catch(Throwable){}
    if(table_exists('kendala_updates')){try{$rows=db()->query("SELECT k.service_number,k.rca FROM kendala_updates k JOIN (SELECT service_number,MAX(id) max_id FROM kendala_updates GROUP BY service_number) x ON x.max_id=k.id ORDER BY k.id DESC")->fetchAll();foreach($rows as $r){$service=trim((string)$r['service_number']);$rca=norm($r['rca']);if($service===''||$rca===''||in_array($rca,['-','N/A','NA','NONE','#N/A'],true))continue;$sto='';if(table_exists('report_area_orders')){$st=db()->prepare('SELECT sto_code FROM report_area_orders WHERE service_number=? ORDER BY period_start DESC LIMIT 1');$st->execute([$service]);$sto=strtoupper(trim((string)($st->fetchColumn()?:'')));}if(in_array($area,['MYR','JGR'],true)&&$sto!==$area)continue;$merged[$service]=['rca'=>$rca,'source'=>'KENDALA'];}}catch(Throwable){}}
    $counts=[];$sheet=0;$kendala=0;foreach($merged as $v){$counts[$v['rca']]=($counts[$v['rca']]??0)+1;$v['source']==='KENDALA'?$kendala++:$sheet++;}arsort($counts);$total=array_sum($counts);$items=[];foreach($counts as $label=>$count)$items[]=['label'=>$label,'count'=>$count,'percent'=>$total?round($count*100/$total,1):0];return['total'=>$total,'items'=>$items,'source'=>'Google Sheet + Grup Kendala','sheet_count'=>$sheet,'kendala_count'=>$kendala];
}

function load_dashboard(string $area,string $period): array {
    $today=new DateTimeImmutable('today');[$start,$end]=period_bounds($today);[$areaSql,$areaParams]=area_condition($area);$p=strtolower(trim($period));$label='Keseluruhan';$time='1=1';$timeParams=[];if($p==='daily'){$time='substr(r.message_date,1,10)=?';$timeParams=[$today->format('Y-m-d')];$label=date_label($today);}elseif($p==='weekly'){$time='r.period_start=?';$timeParams=[$start->format('Y-m-d')];$label=date_label($start).' - '.date_label($end);} $leader=group_report_rows(report_rows("$time AND $areaSql",array_merge($timeParams,$areaParams)));$trend=[];for($i=0;$i<7;$i++){$d=$start->modify("+$i days");$rows=report_rows("substr(r.message_date,1,10)=? AND $areaSql",array_merge([$d->format('Y-m-d')],$areaParams));$services=[];foreach($rows as $r)if(trim((string)$r['service_number'])!=='')$services[$r['service_number']]=1;$trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>count($services)];}$total=array_sum(array_column($leader,'total'));$active=count($leader);return['area'=>strtoupper($area),'period'=>$period,'period_label'=>$label,'summary'=>['total_close'=>$total,'active_technicians'=>$active,'average_close'=>$active?round($total/$active,1):0],'trend'=>$trend,'leaderboard'=>$leader,'rca_summary'=>load_rca_summary($area)];
}

function load_technician(string $identity,string $area): array {
    [$areaSql,$params]=area_condition($area);$rows=report_rows($areaSql,$params);$reg=technician_registry();$members=[];$chosen=['nik'=>'','name'=>'-'];foreach($rows as $r){$nk=norm_name($r['name']);$key=$nk!==''?'NAME:'.$nk:'NIK:'.norm_key($r['nik']);if($key===$identity){$members[]=$r;$chosen=['nik'=>($reg[$nk]['nik']??$r['nik']),'name'=>($reg[$nk]['name']??$r['name'])];}}$today=new DateTimeImmutable('today');[$weekStart]=period_bounds($today);$all=[];$daily=[];$weekly=[];$pairs=[];foreach($members as $r){$s=trim((string)$r['service_number']);if($s==='')continue;$all[$s]=1;if(substr((string)$r['message_date'],0,10)===$today->format('Y-m-d'))$daily[$s]=1;if((string)$r['period_start']===$weekStart->format('Y-m-d'))$weekly[$s]=1;$pairs[$s.'|'.$r['period_start']]=[$s,$r['period_start']];}$orders=[];foreach($pairs as [$s,$ps]){$st=db()->prepare("SELECT r.service_number,substr(MAX(r.message_date),1,10) message_day,COALESCE(NULLIF(TRIM(m.ticket_id),''),NULLIF(TRIM(o.ticket_id),''),'MANUAL') ticket_id,UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''),ra.sto_code,o.sto,''))) area_label,UPPER(TRIM(COALESCE(ra.sto_code,o.sto,''))) sto FROM report_group_orders r LEFT JOIN report_ticket_metadata m ON m.service_number=r.service_number AND m.period_start=r.period_start LEFT JOIN report_area_orders ra ON ra.service_number=r.service_number AND ra.period_start=r.period_start LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1) WHERE r.service_number=? AND r.period_start=? GROUP BY r.service_number,r.period_start");$st->execute([$s,$ps]);$o=$st->fetch();if(!$o)continue;$raw=$o['message_day'];try{$dl=date_label(new DateTimeImmutable($raw));}catch(Throwable){$dl=$raw?:'-';}$orders[]=['service_number'=>$o['service_number'],'ticket_id'=>normalize_ticket($o['ticket_id'])?:'MANUAL','area_label'=>$o['area_label'],'sto'=>$o['sto'],'date_label'=>$dl,'raw_day'=>$raw];}usort($orders,fn($a,$b)=>strcmp($b['raw_day'],$a['raw_day']));foreach($orders as &$o)unset($o['raw_day']);$trend=[];for($i=6;$i>=0;$i--){$d=$today->modify("-$i days");$set=[];foreach($members as $r)if(substr((string)$r['message_date'],0,10)===$d->format('Y-m-d'))$set[$r['service_number']]=1;$trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>count($set)];}return['key'=>$identity,'nik'=>$chosen['nik'],'name'=>$chosen['name'],'daily'=>count($daily),'weekly'=>count($weekly),'all'=>count($all),'orders'=>array_slice($orders,0,100),'trend'=>$trend];
}

function ensure_workflow_tables(): void {
    db()->exec("CREATE TABLE IF NOT EXISTS miniapp_workflow_drafts (telegram_id INTEGER NOT NULL,action TEXT NOT NULL,service_number TEXT NOT NULL,order_json TEXT NOT NULL DEFAULT '{}',data_json TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'draft',updated_at TEXT NOT NULL,PRIMARY KEY(telegram_id,action,service_number))");
    db()->exec("CREATE TABLE IF NOT EXISTS miniapp_completed_workflows (id INTEGER PRIMARY KEY AUTOINCREMENT,technician_id INTEGER NOT NULL,telegram_id INTEGER NOT NULL,action TEXT NOT NULL,service_number TEXT NOT NULL,completed_at TEXT NOT NULL,UNIQUE(telegram_id,action,service_number))");
}

function load_workflow_drafts(int $id): array {if(!technician_by_telegram($id))return['ok'=>false,'error'=>'technician_not_registered'];ensure_workflow_tables();$st=db()->prepare('SELECT action,service_number,order_json,data_json,status,updated_at FROM miniapp_workflow_drafts WHERE telegram_id=? ORDER BY updated_at DESC LIMIT 30');$st->execute([$id]);$items=[];foreach($st->fetchAll() as $r){$r['order']=json_decode($r['order_json']?:'{}',true)?:[];$r['data']=json_decode($r['data_json']?:'{}',true)?:[];unset($r['order_json'],$r['data_json']);$items[]=$r;}return['ok'=>true,'items'=>$items];}

function save_workflow_draft(array $p): array {$id=(string)($p['telegram_id']??'');$action=strtolower(trim((string)($p['action']??'')));$service=norm_key($p['service_number']??'');if(!ctype_digit($id)||!in_array($action,['lengkap','config','report','sto'],true)||$service==='')return['ok'=>false,'error'=>'invalid_draft'];if(!technician_by_telegram((int)$id))return['ok'=>false,'error'=>'technician_not_registered'];ensure_workflow_tables();$status=strtolower((string)($p['status']??''))==='completed'?'completed':'draft';$now=date('Y-m-d\TH:i:s');$st=db()->prepare("INSERT INTO miniapp_workflow_drafts(telegram_id,action,service_number,order_json,data_json,status,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(telegram_id,action,service_number) DO UPDATE SET order_json=excluded.order_json,data_json=excluded.data_json,status=excluded.status,updated_at=excluded.updated_at");$st->execute([(int)$id,$action,$service,json_encode(is_array($p['order']??null)?$p['order']:[],JSON_UNESCAPED_UNICODE),json_encode(is_array($p['data']??null)?$p['data']:[],JSON_UNESCAPED_UNICODE),$status,$now]);return['ok'=>true,'updated_at'=>$now,'status'=>$status];}

function delete_workflow_draft(int $id,string $action,string $service): array {ensure_workflow_tables();$st=db()->prepare('DELETE FROM miniapp_workflow_drafts WHERE telegram_id=? AND action=? AND service_number=?');$st->execute([$id,strtolower(trim($action)),norm_key($service)]);return['ok'=>true];}

function workflow_history(int $id,string $service): array {if(!technician_by_telegram($id))return[];$st=db()->prepare('SELECT id,kind,ticket_id,service_number,old_sn,new_sn,ont_type,sto,valins_id,content,created_at FROM histories WHERE telegram_id=? AND service_number=? ORDER BY created_at,id');$st->execute([$id,$service]);return$st->fetchAll();}

function update_history(int $id,int $historyId,string $content): bool {$st=db()->prepare('UPDATE histories SET content=? WHERE id=? AND telegram_id=?');$st->execute([$content,$historyId,$id]);return$st->rowCount()>0;}

function complete_workflow(array $p): array {$raw=(string)($p['telegram_id']??'');$action=strtolower(trim((string)($p['action']??'')));$service=norm_key($p['service_number']??'');$data=is_array($p['data']??null)?$p['data']:[];$outputs=is_array($p['outputs']??null)?$p['outputs']:[];if(!ctype_digit($raw)||!in_array($action,['lengkap','config','report','sto'],true)||$service==='')return['ok'=>false,'error'=>'invalid_request'];$tech=technician_by_telegram((int)$raw);if(!$tech)return['ok'=>false,'error'=>'technician_not_registered'];$clean=[];foreach($outputs as $o){if(!is_array($o))continue;$kind=strtoupper(trim((string)($o['kind']??'')));$content=trim((string)($o['content']??''));if(in_array($kind,['CONFIG','REPORT','STO'],true)&&$content!=='')$clean[]=[$kind,$content];}if(!$clean)return['ok'=>false,'error'=>'outputs_required'];ensure_workflow_tables();$jagir=false;if(table_exists('jagir_work_orders')){$st=db()->prepare('SELECT 1 FROM jagir_work_orders WHERE service_number=?');$st->execute([$service]);$jagir=(bool)$st->fetchColumn();}$sto=$jagir?'JGR':strtoupper(trim((string)($data['sto']??$tech['sto']??'MYR')));$now=date('Y-m-d\TH:i:s');$historyIds=[];db()->beginTransaction();try{foreach($clean as [$kind,$content]){$st=db()->prepare('SELECT id FROM histories WHERE telegram_id=? AND service_number=? AND kind=? ORDER BY id DESC LIMIT 1');$st->execute([(int)$raw,$service,$kind]);$existing=$st->fetchColumn();$vals=[trim((string)($data['ticket_id']??'MANUAL'))?:'MANUAL',$service,trim((string)($data['old_sn']??'')),trim((string)($data['new_sn']??'')),trim((string)($data['ont_type']??'')),$sto,trim((string)($data['valins_id']??'')),$content];if($existing){$u=db()->prepare('UPDATE histories SET ticket_id=?,service_number=?,old_sn=?,new_sn=?,ont_type=?,sto=?,valins_id=?,content=? WHERE id=? AND telegram_id=?');$u->execute(array_merge($vals,[(int)$existing,(int)$raw]));$historyIds[]=(int)$existing;}else{$u=db()->prepare('INSERT INTO histories(technician_id,telegram_id,kind,ticket_id,service_number,old_sn,new_sn,ont_type,sto,valins_id,content,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)');$u->execute([(int)$tech['id'],(int)$raw,$kind,...$vals,$now]);$historyIds[]=(int)db()->lastInsertId();}}$st=db()->prepare("INSERT INTO miniapp_completed_workflows(technician_id,telegram_id,action,service_number,completed_at) VALUES(?,?,?,?,?) ON CONFLICT(telegram_id,action,service_number) DO UPDATE SET technician_id=excluded.technician_id,completed_at=excluded.completed_at");$st->execute([(int)$tech['id'],(int)$raw,$action,$service,$now]);if($jagir){$st=db()->prepare("UPDATE jagir_work_orders SET status='DONE',assigned_telegram_id=?,assigned_nik=?,assigned_name=?,sto='JGR',area='JAGIR',updated_at=? WHERE service_number=?");$st->execute([(int)$raw,$tech['nik'],$tech['name'],$now,$service]);}$st=db()->prepare('DELETE FROM miniapp_workflow_drafts WHERE telegram_id=? AND action=? AND service_number=?');$st->execute([(int)$raw,$action,$service]);db()->commit();}catch(Throwable $e){db()->rollBack();throw$e;}return['ok'=>true,'action'=>$action,'service_number'=>$service,'history_ids'=>$historyIds,'completed_at'=>$now,'sto'=>$sto,'source'=>$jagir?'WORK ORDER JAGIR':'ORDER SHEET'];}

function load_my_report(int $id): array {$tech=technician_by_telegram($id);if(!$tech)return['ok'=>false,'error'=>'technician_not_registered','message'=>'Akun Telegram belum terdaftar sebagai teknisi.'];$detail=load_technician('NAME:'.norm_name($tech['name']),'ALL');$by=[];foreach($detail['orders'] as $o)$by[$o['service_number']]=$o;ensure_workflow_tables();$st=db()->prepare('SELECT service_number,MAX(completed_at) completed_at FROM miniapp_completed_workflows WHERE telegram_id=? GROUP BY service_number');$st->execute([$id]);foreach($st->fetchAll() as $d){$service=norm_key($d['service_number']);$row=$by[$service]??['service_number'=>$service];$hist=db()->prepare('SELECT ticket_id,sto FROM histories WHERE telegram_id=? AND service_number=? ORDER BY id DESC LIMIT 1');$hist->execute([$id,$service]);$h=$hist->fetch()?:[];$row['raw_day']=substr((string)$d['completed_at'],0,10);$row['date_label']=$row['raw_day']?:'-';$row['ticket_id']=$row['ticket_id']??($h['ticket_id']??'MANUAL');$row['sto']=$row['sto']??($h['sto']??$tech['sto']);$row['area_label']=$row['area_label']??($row['sto']??'-');$row['source']=isset($by[$service])?'miniapp+report':'miniapp';$by[$service]=$row;}$orders=array_values($by);usort($orders,fn($a,$b)=>strcmp((string)($b['raw_day']??''),(string)($a['raw_day']??'')));$today=(new DateTimeImmutable('today'))->format('Y-m-d');[$ws,$we]=period_bounds(new DateTimeImmutable('today'));$daily=0;$weekly=0;foreach($orders as $o){$d=substr((string)($o['raw_day']??''),0,10);if($d===$today)$daily++;if($d!==''&&$d>=$ws->format('Y-m-d')&&$d<=$we->format('Y-m-d'))$weekly++;}$trend=[];for($i=6;$i>=0;$i--){$d=(new DateTimeImmutable('today'))->modify("-$i days");$n=0;foreach($orders as $o)if(substr((string)($o['raw_day']??''),0,10)===$d->format('Y-m-d'))$n++;$trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>$n];}return['ok'=>true,'technician'=>['telegram_id'=>$id,'nik'=>$tech['nik'],'name'=>$tech['name'],'sto'=>$tech['sto']],'daily'=>$daily,'weekly'=>$weekly,'all'=>count($orders),'orders'=>$orders,'trend'=>$trend];}
