<?php
// api/areas_status.php
// Mengembalikan persentase keberhasilan per area.
// Logika: coba hitung dari tabel orders + reports jika tersedia,
// jika gagal, baca tabel area_status sebagai fallback.

header('Content-Type: application/json; charset=utf-8');

require_once __DIR__ . '/../src/lib/db.php'; // sesuaikan path koneksi DB

try {
    // Coba query terkomputasi: jumlah laporan sukses / total orders per area
    $sql = "SELECT a.area_id, a.area_name,
        ROUND(100.0 * SUM(CASE WHEN r.status IN ('success','done','completed','ok') THEN 1 ELSE 0 END) / GREATEST(COUNT(DISTINCT o.order_id),1)) AS success_percent
        FROM areas a
        LEFT JOIN orders o ON o.area_id = a.area_id
        LEFT JOIN reports r ON r.order_id = o.order_id
        GROUP BY a.area_id, a.area_name
        ORDER BY a.area_name";

    $stmt = $db->prepare($sql);
    $stmt->execute();
    $areas = $stmt->fetchAll(PDO::FETCH_ASSOC);

    if ($areas && count($areas) > 0) {
        echo json_encode(['ok' => true, 'source' => 'computed', 'areas' => $areas]);
        exit;
    }
} catch (Exception $e) {
    // Jika query gagal (tabel tidak ada / skema berbeda), lanjut ke fallback
}

try {
    $sql2 = "SELECT area_id, area_name, success_percent FROM area_status ORDER BY area_name";
    $stmt2 = $db->prepare($sql2);
    $stmt2->execute();
    $areas2 = $stmt2->fetchAll(PDO::FETCH_ASSOC);
    echo json_encode(['ok' => true, 'source' => 'area_status_table', 'areas' => $areas2]);
    exit;
} catch (Exception $e) {
    // Semua gagal, kembalikan pesan kosong
    echo json_encode(['ok' => false, 'error' => 'no_data', 'message' => 'Unable to compute area status from DB.']);
    exit;
}
