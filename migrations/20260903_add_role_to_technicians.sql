-- migrations/20260903_add_role_to_technicians.sql
-- Tambah kolom role pada tabel technicians
ALTER TABLE IF EXISTS technicians
  ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'TECHNICIAN';

-- Beri nilai HSA untuk NIK yang diberikan
UPDATE technicians SET role = 'HSA' WHERE nik = '86240021';

-- Contoh: biarkan NIK teknisi kosong agar terisi sendiri oleh teknisi INJOKO (tidak diubah)
