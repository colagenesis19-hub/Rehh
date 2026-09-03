<?php
// src/lib/role_check.php
// Helper middleware untuk memeriksa role sebelum mengizinkan akses ke route tertentu.

function require_role(array $allowed_roles) {
    if (session_status() === PHP_SESSION_NONE) session_start();
    if (empty($_SESSION['user_id'])) {
        http_response_code(401);
        echo json_encode(['ok' => false, 'error' => 'unauthenticated']);
        exit;
    }

    // Ambil role dari tabel technicians
    $userId = $_SESSION['user_id'];
    require_once __DIR__ . '/db.php';
    $stmt = $db->prepare('SELECT role FROM technicians WHERE id = :id LIMIT 1');
    $stmt->execute([':id' => $userId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    $role = $row['role'] ?? 'TECHNICIAN';

    if (!in_array($role, $allowed_roles)) {
        http_response_code(403);
        echo json_encode(['ok' => false, 'error' => 'forbidden']);
        exit;
    }
}
