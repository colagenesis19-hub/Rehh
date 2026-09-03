<?php
// api/me.php
// Mengembalikan informasi user yang sedang login (dengan role).

header('Content-Type: application/json; charset=utf-8');
require_once __DIR__ . '/../src/lib/db.php';
session_start();

if (!empty($_SESSION['user_id'])) {
    $uid = $_SESSION['user_id'];
    $sql = "SELECT id, telegram_id, nik, name, sto, role FROM technicians WHERE id = :id LIMIT 1";
    $stmt = $db->prepare($sql);
    $stmt->execute([':id' => $uid]);
    $me = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($me) {
        echo json_encode(['ok' => true, 'user' => $me]);
        exit;
    }
    echo json_encode(['ok' => false, 'error' => 'not_found']);
    exit;
}

// Jika tidak ada session, kembalikan anonymous/default (frontend akan mengarahkan ke login)
echo json_encode(['ok' => false, 'error' => 'unauthenticated']);
