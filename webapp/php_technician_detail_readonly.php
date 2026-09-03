<?php

declare(strict_types=1);

function technician_detail_readonly(string $identity, string $area): array {
    $identity=trim($identity);
    [$areaSql,$params]=area_condition($area);
    $rows=report_rows($areaSql,$params);
    $techs=dashboard_identity_technicians();

    $target=null;
    if(str_starts_with(strtoupper($identity),'NIK:')){
        $nik=preg_replace('/\D/','',substr($identity,4))?:'';
        foreach($techs as $t){if((string)$t['nik']===$nik){$target=$t;break;}}
    } elseif(str_starts_with(strtoupper($identity),'NAME:')) {
        $target=dashboard_identity_match(substr($identity,5),$techs);
    } else {
        $nik=preg_replace('/\D/','',$identity)?:'';
        if($nik!=='')foreach($techs as $t){if((string)$t['nik']===$nik){$target=$t;break;}}
        if(!$target)$target=dashboard_identity_match($identity,$techs);
    }

    $members=[];
    foreach($rows as $r){
        $rawNik=preg_replace('/\D/','',(string)($r['nik']??''))?:'';
        $rawName=(string)($r['name']??'');
        $rowMatch=dashboard_identity_match($rawName,$techs);
        if($target){
            if(($rawNik!=='' && $rawNik===(string)$target['nik']) || ($rowMatch && (string)$rowMatch['nik']===(string)$target['nik'])) $members[]=$r;
        } else {
            $nk=norm_name($rawName);
            $key=$nk!==''?'NAME:'.$nk:'NIK:'.norm_key($r['nik']??'');
            if($key===$identity)$members[]=$r;
        }
    }

    $chosen=$target?:['nik'=>'','name'=>'-','sto'=>''];
    if(!$target && $members){$first=$members[0];$chosen=['nik'=>(string)($first['nik']??''),'name'=>(string)($first['name']??'-'),'sto'=>(string)($first['sto']??'')];}

    $today=new DateTimeImmutable('today');[$weekStart]=period_bounds($today);
    $all=[];$daily=[];$weekly=[];$pairs=[];
    foreach($members as $r){$s=trim((string)($r['service_number']??''));if($s==='')continue;$all[$s]=1;if(substr((string)($r['message_date']??''),0,10)===$today->format('Y-m-d'))$daily[$s]=1;if((string)($r['period_start']??'')===$weekStart->format('Y-m-d'))$weekly[$s]=1;$pairs[$s.'|'.($r['period_start']??'')]=[$s,(string)($r['period_start']??'')];}

    $orders=[];
    foreach($pairs as [$s,$ps]){$st=db()->prepare("SELECT r.service_number,substr(MAX(r.message_date),1,10) message_day,COALESCE(NULLIF(TRIM(m.ticket_id),''),NULLIF(TRIM(o.ticket_id),''),'MANUAL') ticket_id,UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''),ra.sto_code,o.sto,''))) area_label,UPPER(TRIM(COALESCE(ra.sto_code,o.sto,''))) sto FROM report_group_orders r LEFT JOIN report_ticket_metadata m ON m.service_number=r.service_number AND m.period_start=r.period_start LEFT JOIN report_area_orders ra ON ra.service_number=r.service_number AND ra.period_start=r.period_start LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1) WHERE r.service_number=? AND r.period_start=? GROUP BY r.service_number,r.period_start");$st->execute([$s,$ps]);$o=$st->fetch();if(!$o)continue;$raw=$o['message_day'];try{$dl=date_label(new DateTimeImmutable($raw));}catch(Throwable){$dl=$raw?:'-';}$orders[]=['service_number'=>$o['service_number'],'ticket_id'=>normalize_ticket($o['ticket_id'])?:'MANUAL','area_label'=>$o['area_label'],'sto'=>$o['sto'],'date_label'=>$dl,'raw_day'=>$raw];}
    usort($orders,fn($a,$b)=>strcmp((string)$b['raw_day'],(string)$a['raw_day']));foreach($orders as &$o)unset($o['raw_day']);unset($o);

    $trend=[];for($i=6;$i>=0;$i--){$d=$today->modify("-$i days");$set=[];foreach($members as $r)if(substr((string)($r['message_date']??''),0,10)===$d->format('Y-m-d')){$s=trim((string)($r['service_number']??''));if($s!=='')$set[$s]=1;}$trend[]=['date'=>$d->format('Y-m-d'),'label'=>DAYS_ID[((int)$d->format('N'))-1],'total'=>count($set)];}

    return ['key'=>$target?'NIK:'.$target['nik']:$identity,'nik'=>(string)($chosen['nik']??''),'name'=>(string)($chosen['name']??'-'),'daily'=>count($daily),'weekly'=>count($weekly),'all'=>count($all),'orders'=>array_slice($orders,0,100),'trend'=>$trend];
}
