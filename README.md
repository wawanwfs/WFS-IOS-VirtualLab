# WFS iOS Virtual Lab — Fase 1 (eksperimental)

Dashboard lokal dan harness riset dalam container untuk target QEMU HakiOS: kernel XNU sumber-terbuka yang di-port ke ARM64, dijalankan di atas QEMU di workstation x86_64 lewat emulasi.

> **Yang perlu dipahami sejak awal.** Repo ini **tidak** berisi iOS, firmware proprietary Apple, file IPSW, atau simulator iPhone yang kompatibel dengan semua aplikasi. Image sistem iOS dibuat di mesin Anda sendiri dari IPSW yang Anda unduh dan olah secara eksplisit (lihat [Menyiapkan HakiOS dan image iOS](#menyiapkan-hakios-dan-image-ios)). Tidak ada akun Apple, unduhan App Store, seluler, atau dukungan IPA umum yang dijanjikan. Boot lewat emulasi itu lambat: pada validasi yang tercatat, boot satu CPU sampai Home Screen memakan waktu sekitar 38 menit.

## Daftar isi

- [Ringkasan](#ringkasan)
- [Fitur](#fitur)
- [Arsitektur](#arsitektur)
- [Persyaratan](#persyaratan)
- [Mulai cepat](#mulai-cepat)
- [Dashboard](#dashboard)
- [Menyiapkan HakiOS dan image iOS](#menyiapkan-hakios-dan-image-ios)
- [Konfigurasi](#konfigurasi)
- [API](#api)
- [Menggunakan sesi](#menggunakan-sesi)
- [Pemecahan masalah](#pemecahan-masalah)
- [Validasi yang sudah dilakukan](#validasi-yang-sudah-dilakukan)
- [Keamanan dan batasan](#keamanan-dan-batasan)
- [Struktur proyek](#struktur-proyek)
- [Pengembangan dan pengujian](#pengembangan-dan-pengujian)
- [Rencana Fase 2](#rencana-fase-2)
- [Sumber](#sumber)

## Ringkasan

WFS iOS Virtual Lab adalah satu layanan container yang berisi tiga hal:

1. **Manager FastAPI** (`app/main.py`) yang memeriksa prasyarat, menjalankan tepat satu sesi QEMU, menghentikannya dengan batas waktu, dan melaporkan status serta log sesi.
2. **Dashboard web** berbahasa Indonesia (`app/static/index.html`) untuk memulai/menghentikan sesi, melihat status, dan membaca log — tanpa perlu menyentuh terminal setelah container jalan.
3. **Tampilan virtual noVNC** yang menampilkan desktop X11 virtual tempat jendela GTK QEMU berjalan, sehingga layar iPhone bisa dilihat dan disentuh dari browser.

Proyek ini ditujukan untuk riset di workstation tepercaya milik satu pengguna. Bukan layanan hosting, bukan produk untuk banyak pengguna, dan bukan jalan pintas untuk memakai layanan Apple.

## Fitur

- **Pemeriksaan prasyarat sebelum start.** Sesi ditolak dengan HTTP 409 dan daftar nama file yang kurang, bukan gagal diam-diam di tengah jalan. Setiap prasyarat yang kurang ditampilkan di dashboard beserta cara memperbaikinya.
- **Satu sesi dalam satu waktu.** Start kedua saat sesi berjalan ditolak dengan HTTP 409. Sesi berhenti otomatis saat durasi habis (durasi + 40 detik untuk shutdown loader).
- **Deteksi kernel panic.** Jika guest mencetak baris `panic(cpu ...)` sementara proses QEMU masih hidup, status guest dilaporkan `failed` dan dashboard menampilkan banner kesalahan kernel.
- **Shutdown yang bersih.** Stop mengirim SIGTERM ke seluruh grup proses sesi, lalu SIGKILL jika masih hidup, termasuk anak proses yang mengabaikan SIGTERM.
- **Input sentuh yang disesuaikan untuk emulasi lambat.** Gerakan hover tidak dikirim ke guest, update saat drag dibatasi 10 per detik, dan pointer yang tertahan dilepas saat browser kehilangan fokus atau tab disembunyikan. Kursor crosshair tetap terlihat meski QEMU menyembunyikan kursor tabletnya.
- **Staging runtime di volume Linux.** File kerja QEMU dan RAM guest disiapkan di volume Docker `qemu-runtime` (`/var/lib/wfs`), bukan di bind mount host, supaya pemetaan memori guest cepat dan berperilaku seperti filesystem Linux. Start pertama men-stage salinan file (sekitar 2,4 GB); start berikutnya memakai ulang salinan yang tidak berubah.
- **Image alternatif tanpa merusak yang asli.** Image sistem alternatif diperiksa sebelum start dan di-stage ke runtime tanpa mengganti image sumber.
- **Dashboard tanpa cache basi.** Dashboard disajikan dengan `Cache-Control: no-store`, jadi perubahan kode tampilan langsung terlihat tanpa `Ctrl+F5`.

## Arsitektur

```text
Browser ── http://localhost:8000 ──► FastAPI manager (uvicorn, :8000)
   │                                    │
   │  POST /api/start                  ▼
   │                            app/launch.py
   │                              (stage ke /var/lib/wfs/hakios)
   │                                    │
   │                                    ▼
   │                            qemu/run-ios.sh <detik> -display gtk -nic none
   │                                    │
   │                                    ▼
   │                            QEMU ARM64 (virt, Cortex-A76, TCG)
   │                            XNU loader + kernel + image APFS
   │                                    │
   │                                    ▼ (jendela GTK)
   └─ http://localhost:6080/vnc.html ─► noVNC ─► websockify (:6080)
                                              ─► x11vnc (:5900, localhost saja)
                                              ─► Xvfb :99 (1125x2500x24)
```

Alur datanya:

| Komponen | Peran | Port / lokasi |
|---|---|---|
| FastAPI + Uvicorn | API manager sesi, disajikan dari venv `/opt/wfs/.venv` di dalam container | `127.0.0.1:8000` (host) → `:8000` (container) |
| noVNC + websockify | Tampilan virtual di browser | `127.0.0.1:6080` (host) → `:6080` (container) |
| x11vnc | Menangkap desktop X11 virtual | `127.0.0.1:5900` di dalam container saja |
| Xvfb | Desktop X11 virtual `:99` | `1125x2500x24` |
| Volume `qemu-runtime` | Salinan runtime Linux + RAM guest (sparse `qemu/ram.img`) | `/var/lib/wfs` |
| Bind mount `./workspace` | Sumber HakiOS, image APFS, dan log yang persisten di host | `/workspace` di container |

Di dalam container, HakiOS berada di `/workspace/hackios` (bind mount `./workspace/` di host). Image default berada di `/workspace/hackios/userland/system.apfs`. Kalau manager dijalankan secara native tanpa Docker dengan `WFS_WORKSPACE=$PWD`, HakiOS berada di `./hackios` di root repo. Kedua layout itu sama-sama didukung karena manager membaca lokasi dari `WFS_WORKSPACE`.

Manager menjalankan launcher persis seperti yang didokumentasikan upstream, ditambah argumen tampilan dan jaringan:

```bash
bash qemu/run-ios.sh 1200 -display gtk -nic none
```

Durasi diteruskan sebagai argumen posisi pertama, GTK diaktifkan di `DISPLAY=:99`, dan API membatasi waktu dinding sesi sampai durasi + 40 detik. Manager mendukung layout launcher HakiOS yang terpasang dan path firmware AAVMF Ubuntu; path firmware diteruskan lewat variabel lingkungan `QEMU_EFI`/`QEMU_VARS` ke proses sesi.

## Persyaratan

- **OS dan container:** Linux x86_64 dengan Docker Engine + Docker Compose v2, atau Windows 11 dengan WSL2 dan Docker Desktop (container Linux). Jalur yang tervalidasi memakai Docker Desktop di Windows; lihat [Validasi yang sudah dilakukan](#validasi-yang-sudah-dilakukan).
- **RAM:** disarankan **≥ 16 GB**. Minimum upstream HakiOS lebih rendah, tetapi profil yang tervalidasi memakai RAM guest 7–10 GB. Perlu dipahami cara kerja RAM-nya: `QEMU_RAM_GB` (default 7) adalah ukuran ruang alamat guest; file `qemu/ram.img` yang dipetakan sebagai RAM guest berukuran 12 GB secara logis tetapi sparse, dan satu instance memakai sekitar 2,5–3 GB memori host. Launcher HakiOS sendiri menolak start kalau memori host yang tersedia di bawah 3 GB (kecuali `QEMU_FORCE=1`).
- **Disk:** disarankan **≥ 30 GB kosong**. Pengambilan image butuh sekitar 8 GB selama proses dan 5,3 GB setelahnya; start pertama men-stage sekitar 2,4 GB ke volume runtime; image sistem yang dibangun berukuran sekitar 2,5 GB; ditambah sumber HakiOS dan file `ram.img` sparse 12 GB (logis).
- **CPU:** host x86_64 bekerja lewat **emulasi TCG**, bukan akselerasi ARM KVM. Boot bisa sangat lambat. Jangan berharap kecepatan mendekati perangkat nyata.
- **Internet:** untuk clone sumber HakiOS dan pengambilan IPSW dari CDN Apple, setelah meninjau hak dan ketentuan lisensi yang berlaku untuk Anda.
- **Perangkat lunak build (di dalam container):** image Docker sudah berisi QEMU ARM64, firmware AAVMF, SeaBIOS/ramfb, Xvfb, x11vnc, noVNC, websockify, 7-Zip, lz4, dan toolchain build. Untuk langkah `fetch.sh`/`build.sh` di luar container, dibutuhkan `python3`, `7z` versi 23 atau lebih baru (karena bisa membaca APFS), dan `cc`.

## Mulai cepat

```bash
docker compose up -d --build
# Dashboard: http://localhost:8000
# Tampilan QEMU: http://localhost:6080/vnc.html
```

Perintah lain yang sering dipakai:

```bash
docker compose logs -f --tail=80 wfs-ios-lab   # ikuti log container
docker compose ps                              # status container + healthcheck
docker compose down                            # hentikan container
docker compose build --no-cache                # build ulang bersih (mis. setelah ganti file proyek)
```

**Yang langsung bisa dilakukan sebelum image iOS ada:** dashboard tetap bisa dibuka dan `GET /api/status` melaporkan `ready: false` beserta daftar prasyarat yang kurang. Itu perilaku yang benar, bukan error. Sesi baru bisa dimulai setelah prasyarat lengkap (lihat langkah berikutnya). Menjalankan Docker saja tidak membuktikan HakiOS bisa boot; prasyarat HakiOS tetap terpisah.

## Dashboard

Dashboard berbahasa Indonesia dan terdiri dari:

- **Tampilan Virtual** — frame portrait layar ponsel (noVNC). Ada tombol muat ulang tampilan dan tautan untuk membuka tampilan di tab baru, berguna kalau frame yang tertanam terasa sempit.
- **Kontrol Sesi** — preset durasi (1, 5, 20, 60 menit) atau angka bebas 60–3600 detik, tombol Mulai sesi dan Berhenti. Tombol Berhenti harus diklik dua kali dalam 4 detik, supaya boot yang lambat tidak mati karena satu klik yang tidak disengaja.
- **Diagnostik** — checklist repositori, userland, dan image APFS, plus daftar setiap prasyarat yang kurang beserta label dan langkah perbaikannya. Banner merah muncul kalau guest mengalami kernel panic; banner kuning muncul kalau RAM guest tidak muat di RAM host.
- **Sistem** — CPU dan RAM host, CPU dan RAM guest, durasi default, dan kode keluar sesi terakhir.
- **Log Sesi Terakhir** — 20 KB terakhir dari log sesi, dengan refresh otomatis (bisa dimatikan), gulir otomatis, tombol salin, dan tombol muat ulang. Polling status berhenti saat tab disembunyikan dan dilanjutkan saat tab kembali terlihat.

### Mode dashboard saja (tanpa Docker, tanpa guest)

Mode ini berguna untuk memeriksa manager itu sendiri, menjalankan regression test secara manual, atau melihat checklist prasyarat di mesin yang belum punya Docker:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
WFS_WORKSPACE=$PWD .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000 — /api/status melaporkan ready:false sampai HakiOS dan image tersedia
```

Mode ini tidak menyediakan QEMU, firmware, Xvfb, maupun noVNC, jadi tampilan virtual (port 6080) tidak ada dan sesi guest tidak bisa dimulai. Untuk sesi guest, jalankan lewat Docker Compose.

## Menyiapkan HakiOS dan image iOS

Urutan langkahnya harus diikuti apa adanya: **bootstrap → fetch → build**. Jangan melompati `fetch.sh`: image tidak diunduh otomatis oleh manager, dan tidak ada image bawaan di repo ini.

### 1. Bootstrap sumber HakiOS

Jalankan dari dalam container:

```bash
docker compose exec wfs-ios-lab bash /opt/wfs/scripts/bootstrap.sh
```

Bootstrap meng-clone `https://github.com/oosexgang/hakios-xnu-kernel.git` (tanpa checkout) lalu checkout terpisah (detached) di commit yang dipin:

```text
88513176b1e96ecf0b764cd62c6f4e6ac71345e3
```

Commit pin ini cocok dengan layout launcher (`qemu/run-ios.sh`) yang dipakai manager. Checkout yang sudah ada dipertahankan dan tidak di-clone ulang. `WFS_HAKIOS_REV` bisa meng-override revisi untuk instalasi baru, tetapi hanya setelah peninjauan kompatibilitas — layout launcher bisa berubah antar revisi upstream.

### 2. Fetch: unduh dan ekstrak file iOS dari IPSW

**Baca dulu ketentuan hukumnya.** Baca `LEGAL.md` dan `COMPLIANCE.md` di sumber HakiOS sebelum langkah ini. HakiOS adalah proyek riset open-source yang tidak berafiliasi dengan Apple. Repo HakiOS tidak mendistribusikan bagian apa pun dari iOS; image userland dibangun di mesin Anda dari IPSW iOS 16.5 yang diunduh dari server publik Apple di bawah lisensi Apple, hanya untuk mesin Anda. Apakah penggunaan itu sah di yurisdiksi Anda adalah tanggung jawab Anda. Jangan mendistribusikan hasil ekstrak IPSW, image userland, atau file-file di dalamnya tanpa hak yang sesuai.

```bash
# Periksa dulu sumber dan ketentuan hukumnya, lalu:
docker compose exec wfs-ios-lab bash -lc 'cd /workspace/hackios && bash sysimage/fetch.sh'
```

Yang dilakukan `sysimage/fetch.sh` (iOS 16.5, build 20F66, iPhone X):

- Membaca anggota arsip yang dibutuhkan saja dari IPSW di CDN Apple lewat HTTP range request (`fetch-from-ipsw.py`), tanpa mengunduh seluruh IPSW 6,2 GB: image root filesystem 4,7 GB, image OS cryptex 2,7 GB, dan cryptex aplikasi. Unduhan yang terputus dilanjutkan dari posisi terakhir untuk anggota yang disimpan tanpa kompresi.
- Memilih subset root filesystem (`select-system.py`), membuat kerangka `/private/var` (`mkvarskel.py`), mengekstrak dengan 7z, dan menyelesaikan file yang terkompresi LZBITMAP dengan `unzbm` (dibangun dari `xnu-deps` dengan `cc`).
- Hasilnya diletakkan di `sysimage/`: `rootfs/`, `system.files`/`.manifest`, `var.skel`, `cryptex/`, `cryptex-app/`, dan cache dyld `20F66__iPhone10,3_6/`.

Kebutuhan dan perilaku penting:

- Dibutuhkan `python3`, `7z` (7-Zip 23 atau lebih baru, karena membaca APFS), dan `cc`. Sekitar 8 GB disk selama proses berjalan dan 5,3 GB setelah selesai.
- Secara default image `.dmg` yang diunduh dihapus setelah diekstrak. Set `KEEP=1` untuk menyimpannya; `rootfs.dmg` hanya dibutuhkan lagi kalau `select-system.py` diubah, dan proses kedua tidak mengunduh apa pun kalau file itu masih ada.
- Langkah-langkahnya ditandai file `.done-rootfs` dan `.done-cryptex`, jadi menjalankan ulang `fetch.sh` bersifat inkremental dan aman.
- `fetch.sh` menulis `rootfs.slt`, `extract-system.log`, dan `extract-cryptex.log` di `sysimage/` untuk diagnosis.

### 3. Build: buat image APFS root dan sistem

```bash
docker compose exec wfs-ios-lab bash -lc 'cd /workspace/hackios && REST=1 bash userland/build.sh'
```

Yang dibuat `userland/build.sh`:

| Output | Isi |
|---|---|
| `userland/root.apfs` | Image kecil: init dan program uji, `etc/rc`, job launchd, dan volume boot. Dibangun ulang setiap kali. |
| `userland/system.apfs` | Image sistem (sekitar 2,5 GB): subset root filesystem iOS 16.5 di path aslinya, dyld shared cache, dan `src/stage0.c` sebagai `/sbin/launchd`. Dibangun ulang kalau hilang, kalau inputnya (stage0, manifest, file cryptex) lebih baru, atau dengan `SYSTEM=1`. |

Opsi build yang relevan di sini:

| Variabel | Arti |
|---|---|
| `REST=1` | Muat sisa job launchd iOS, bukan hanya daftar default. **Dipakai untuk sesi dashboard standar.** |
| `PREBUILT=1` | Jangan compile apa pun; pakai program dari `prebuilt/userland`. Ini juga yang terjadi otomatis kalau toolchain cross (`ld64`) tidak tersedia. |
| `CHECK=1` | Periksa setiap image saat dibuat (APFS harus bersih dan bisa dibaca kembali). Image sistem butuh beberapa menit ekstra. |
| `SYSTEM=1` | Bangun ulang `system.apfs` meski inputnya tidak berubah. |
| `QUIET=1` | Kurangi noise console launchd. |

Peringatan dari header `build.sh` yang wajib diperhatikan: direktori `sysimage/rootfs`, `sysimage/cryptex`, dan `sysimage/cryptex-app` harus berupa direktori milik salinan ini sendiri (hard link), bukan symlink ke salinan lain. Membangun dengan symlink bisa merusak tree bersama saat `rm -rf`/`mv` berjalan. Kalau ragu, buat salinan kerja baru dengan `tools/new-workspace.sh`.

Setelah build selesai, buka dashboard, atur durasi sesi, dan klik **Mulai sesi**. Perintah standar upstream yang setara, untuk dijalankan manual di dalam container:

```bash
cd /workspace/hackios
bash qemu/run-ios.sh 1200 -display gtk
```

## Konfigurasi

Konfigurasi dibaca dari variabel lingkungan. Di Docker, atur lewat file `.env` lokal di root repo (salin dari `.env.example`); file `.env` tidak di-commit. Di mode native, set variabelnya di shell sebelum menjalankan Uvicorn.

| Variabel | Default | Arti |
|---|---|---|
| `WFS_WORKSPACE` | `/workspace` (container) | Root workspace: lokasi `hackios/` dan `logs/`. |
| `WFS_SESSION_SECONDS` | `3600` (Compose), `1200` (tanpa env) | Durasi default sesi, dibatasi 60–3600 detik. Nilai di luar rentang atau bukan angka kembali ke default. |
| `WFS_SYSTEM_IMAGE` | `/workspace/hackios/userland/system.apfs` | Path image sistem di dalam container. Image alternatif diperiksa sebelum start dan di-stage tanpa mengganti image asli. |
| `QEMU_RAM_GB` | `7` | RAM guest dalam GB. Profil validasi memakai `10` untuk image cache-tanpa-kompresi (sekitar 4,21 GB). |
| `WFS_QEMU_CPUS` | `1` | Jumlah CPU emulasi (`QEMU_SMP` di Compose). Profil generik memakai 1; lihat catatan CPU di bawah. |
| `WFS_QEMU_BOOT_ARGS` | _(kosong)_ | Argumen boot kernel tambahan, diteruskan lewat `CMDLINE` bersama `cpus=N`. |
| `WFS_HAKIOS_REV` | `8851317…` (pin) | Revisi HakiOS untuk instalasi bootstrap baru. |
| `QEMU_EFI` / `QEMU_VARS` | `/usr/share/AAVMF/AAVMF_CODE.fd` / `AAVMF_VARS.fd` | Firmware UEFI AArch64. Manager meneruskan default Ubuntu ini ke sesi; `qemu/run.sh` upstream sendiri default ke path Arch/EDK2. |
| `QEMU_SMP` | dari `WFS_QEMU_CPUS` | Diteruskan ke QEMU oleh `qemu/run.sh`. |
| `WFS_RUNTIME` | `/var/lib/wfs/hakios` | Direktori staging runtime Linux (hanya dipakai `app/launch.py`). |

Contoh `.env` untuk workstation yang sudah tervalidasi (bukan default repo — lihat bagian validasi):

```dotenv
WFS_SYSTEM_IMAGE=/workspace/hackios/userland/system.apfs
QEMU_RAM_GB=7
WFS_QEMU_CPUS=1
WFS_QEMU_BOOT_ARGS=
```

### Catatan CPU dan boot-arg

Profil generik memakai **satu CPU emulasi**. Profil empat CPU yang tidak dimodifikasi sebelumnya mengalami kernel panic (spinlock tiket, lihat [Validasi](#validasi-yang-sudah-dilakukan)). Pada workstation validasi, profil lokal delapan CPU memakai argumen boot berikut untuk memperpanjang timeout ticket/spinlock XNU menjadi 30 detik, supaya emulasi perangkat lunak punya waktu:

```dotenv
WFS_QEMU_CPUS=8
WFS_QEMU_BOOT_ARGS=tlto_us=30000000 slto_us=30000000
```

Preflight delapan CPU lolos pemeriksaan init, service, dan surface, tetapi itu **preflight, bukan bukti** Home Screen interaktif delapan CPU. Emulasi tetap lambat apa pun profilnya; pilih durasi sesi 60–3600 detik sesuai kebutuhan dan biarkan sesi berjalan.

## API

Base URL dashboard: `http://localhost:8000`. Semua respons berformat JSON, kecuali `/` (HTML) dan `/api/logs` (teks biasa).

### `GET /api/status`

Status VM, pemeriksaan instalasi, dan timing sesi. Contoh ringkas saat prasyarat belum lengkap:

```json
{
  "status": "stopped",
  "repository_present": true,
  "userland_present": true,
  "images_present": false,
  "session_seconds_default": 3600,
  "host_logical_cpus": 8,
  "host_memory_gb": 19.9,
  "guest_cpus": 1,
  "guest_ram_gb": 7,
  "guest_ram_fits_host": true,
  "ready": false,
  "missing": ["root_image", "system_image"],
  "missing_details": [
    {
      "name": "root_image",
      "label": "Image root APFS (userland/root.apfs)",
      "fix": "Jalankan fetch.sh, lalu REST=1 bash userland/build.sh di hackios/."
    }
  ],
  "session_elapsed_seconds": null,
  "session_seconds_remaining": null,
  "last_exit_code": null,
  "guest_status": "stopped",
  "guest_error": null
}
```

Arti field utama:

| Field | Arti |
|---|---|
| `status` | `running` atau `stopped` (proses manager sesi). |
| `repository_present` / `userland_present` / `images_present` | Apakah launcher HakiOS, direktori userland, dan kedua image APFS ada. |
| `host_logical_cpus` / `host_memory_gb` | CPU logis dan total RAM host (GB, `null` kalau tidak bisa dibaca). |
| `guest_cpus` / `guest_ram_gb` / `guest_ram_fits_host` | Konfigurasi guest dan apakah RAM guest muat di RAM host. |
| `ready` | `true` hanya kalau `missing` kosong. |
| `missing` / `missing_details` | Nama prasyarat yang kurang, plus label dan langkah perbaikan untuk dashboard. |
| `session_elapsed_seconds` / `session_seconds_remaining` | Waktu sesi yang berjalan (`null` saat tidak ada sesi berjalan). |
| `last_exit_code` | Kode keluar proses sesi terakhir (`null` kalau belum pernah start). |
| `guest_status` | `stopped`, `unverified` (berjalan, belum ada bukti panic), atau `failed` (guest mencetak panic). |
| `guest_error` | Baris panic pertama dari guest, atau `null`. |

Prasyarat yang diperiksa (`missing` memakai nama-nama ini): `launcher`, `qemu_runner`, `payload_builder`, `root_image`, `system_image`, `kernel`, `loader`, `efi`, `efi_vars`, `ramfb_rom`. File yang kosong (0 byte) dianggap hilang.

### `POST /api/start`

Memulai tepat satu sesi. Body harus JSON dengan `seconds` bilangan bulat 60–3600:

```bash
curl -X POST http://localhost:8000/api/start \
  -H 'Content-Type: application/json' -d '{"seconds": 1200}'
# {"status": "starting", "pid": 1234}
```

| Situasi | Respons |
|---|---|
| Sesi sudah berjalan | `409 Session already running` |
| Prasyarat kurang | `409 Missing prerequisites: root_image, system_image` |
| Launcher tidak bisa dijalankan | `503 Cannot launch session: ...` |
| `seconds` di luar 60–3600, bukan bilangan bulat, boolean, atau null | `422` (validasi Pydantic, `strict=True`) |

Nilai `seconds` diteruskan apa adanya sebagai argumen posisi ke launcher; jangan pernah menginterpolasikannya ke shell — manager memakai `subprocess.Popen` dengan daftar argumen.

### `POST /api/stop`

Menghentikan sesi yang berjalan (SIGTERM ke grup proses, lalu SIGKILL bila perlu). Selalu mengembalikan `{"status": "stopped"}`, termasuk kalau tidak ada sesi berjalan. Sesi juga berhenti otomatis lewat timer internal, dan dihentikan saat API shutdown.

### `GET /api/logs`

Teks biasa: 20 KB terakhir dari `logs/session.log` (di dalam container: `/workspace/logs/session.log`). Kalau belum ada log, mengembalikan `No session logs yet.`

### Perilaku sesi yang perlu diketahui

- State sesi hidup di dalam proses API. Setelah service restart, manager **tidak** menempel kembali (reattach) ke proses QEMU yang sudah berjalan sebelumnya.
- Timer sesi terikat pada satu proses: timer lama tidak bisa menghentikan sesi yang lebih baru (diuji oleh regression test).
- Output serial guest di-buffer dan ditulis ke log bind mount sekali per detik, bukan per byte, supaya filesystem host (mis. bind mount Windows) tidak dibanjiri write kecil.

## Menggunakan sesi

1. Buka `http://localhost:8000`, periksa panel Diagnostik sampai tidak ada prasyarat yang kurang.
2. Pilih durasi. Untuk boot pertama, pakai durasi panjang (mis. 3600 detik): boot emulasi bisa memakan waktu puluhan menit dan sesi yang keburu habis akan memotong boot di tengah jalan.
3. Klik **Mulai sesi**, lalu buka tampilan di `http://localhost:6080/vnc.html` (atau frame yang tertanam di dashboard). Logo Apple yang muncul menandakan guest benar-benar boot, bukan sekadar container yang jalan.
4. Sentuh dengan klik; seret dari tepi bawah ke atas untuk Home; tekan `L` untuk kunci/bangun, `H` untuk Home, dan `Up`/`Down` untuk volume (tombol-tombol ini diteruskan QEMU sebagai tombol perangkat). Hover tidak dikirim ke guest — hanya klik/drag yang menjadi sentuhan.
5. Klik **Berhenti** dua kali untuk mengakhiri sesi lebih awal. Jangan menutup browser saja: sesi tetap berjalan di server sampai durasinya habis atau dihentikan lewat API.

Catatan soal log: setiap baris console guest keluar **dua kali** di log sesi (blok yang diputar ulang ribuan baris kemudian, perilaku launcher upstream). Jangan menghitung kejadian dengan `grep -c`; hitung kejadian yang berbeda — berdasarkan timestamp, atau program dan PID untuk baris seperti `Successfully spawned`.

## Pemecahan masalah

| Gejala | Penyebab yang paling mungkin | Perbaikan |
|---|---|---|
| `GET /api/status` melaporkan `ready: false` | Prasyarat belum lengkap | Ikuti daftar `missing_details` di dashboard, sesuai urutan bootstrap → fetch → build. |
| `exec: uvicorn: not found` saat container start | File proyek diganti tanpa rebuild, atau image lama | Project menginstall FastAPI/Uvicorn di `/opt/wfs/.venv` dan memanggilnya lewat Python venv itu. Build ulang bersih: `docker compose down && docker compose build --no-cache && docker compose up -d`, lalu cek `docker compose logs -f --tail=80 wfs-ios-lab` dan `http://localhost:8000/api/status`. |
| Sesi langsung `stopped`, `last_exit_code` bukan 0 | Launcher gagal (mis. image hilang) | Baca `GET /api/logs`. Manager menolak start kalau prasyarat kurang; kalau launcher gagal di tengah jalan, kode keluarnya dilaporkan di status. |
| Banner `GAGAL`, `guest_error` berisi `Ticket spinlock timeout` | Kernel panic spinlock saat scheduling thread (tercatat pada profil 4 CPU) | Kembali ke 1 CPU (`WFS_QEMU_CPUS=1`, tanpa boot-arg tambahan), atau pakai profil 8 CPU + timeout 30 detik dari [Konfigurasi](#konfigurasi). Hentikan sesi, periksa log, lalu start ulang. |
| Boot sangat lambat / layar lama kosong | Emulasi TCG di x86_64, bukan akselerasi KVM | Normal untuk proyek ini. Boot 1 CPU sampai Home Screen tercatat sekitar 38 menit. Jangan menghentikan sesi hanya karena lambat; pakai durasi maksimal. |
| `run-ios.sh: only ... MB of memory available` | Memori host tersedia < 3 GB | Hentikan QEMU lain / bebaskan memori. `QEMU_FORCE=1` memaksa start, tetapi berisiko proses lain terbunuh (OOM). |
| Tampilan noVNC hitam / tidak terhubung | `websockify`/`x11vnc` belum siap, atau port 6080 belum terekspos | Tunggu healthcheck container `healthy`, muat ulang tampilan dari dashboard, atau buka `http://localhost:6080/vnc.html` langsung. Di mode native tanpa Docker, tampilan memang tidak ada. |
| Dashboard menampilkan versi lama | Cache browser (instalasi lama) | Versi sekarang memakai `Cache-Control: no-store`. Untuk instalasi lama, paksa refresh dengan `Ctrl+F5`. |
| `fetch.sh: 7z is not installed` / 7z terlalu lama | `fetch.sh` butuh 7-Zip 23+ | Install paket `7zip` (Ubuntu 24.04: 7-Zip 23.01). Versi lama tidak bisa membaca APFS. |
| `fetch.sh` terputus di tengah unduhan | Jaringan / proxy | Jalankan ulang `fetch.sh`: unduhan anggota yang disimpan tanpa kompresi dilanjutkan dari posisi terakhir, dan langkah yang sudah `.done` dilewati. |
| `build.sh: sysimage/... is a symlink` | Tree `sysimage` berupa symlink ke salinan lain | Hapus symlink dan salin ulang sebagai direktori hard link milik salinan ini (lihat `tools/new-workspace.sh`). Jangan membangun dengan symlink. |
| `docker compose up` gagal build | Cache build lama / dependensi berubah | `docker compose build --no-cache`, lalu `up -d`. Periksa log build untuk paket apt/pip yang gagal. |

Kalau masalahnya tidak ada di tabel ini, sertakan output `GET /api/status`, 20 KB terakhir `GET /api/logs`, dan `docker compose logs --tail=80 wfs-ios-lab` saat melaporkan — tiga sumber itu hampir selalu cukup untuk membedakan masalah prasyarat, masalah guest, dan masalah container.

## Validasi yang sudah dilakukan

Ringkasan dari `docs/VALIDATION.md` (31 Oktober 2026, Asia/Jakarta). Detail lengkap, file bukti, dan log ada di dokumen itu dan di `artifacts/`. **Baca bagian ini apa adanya: yang tervalidasi dicatat sebagai tervalidasi, yang masih preflight dicatat sebagai preflight.**

Lingkungan validasi: host Windows, Docker Desktop (container Linux), sekitar 9,7 GiB dialokasikan ke Docker, CPU Intel Core i5-8250U (4 core, 8 thread), RAM fisik sekitar 19,9 GiB. Container Ubuntu 24.04, QEMU 8.2.2, Python 3.12.3, FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.2. Sumber HakiOS terpasang di commit pin yang sama dengan bootstrap di atas; kernel dan loader cocok dengan SHA-256 di `prebuilt/SHA256SUMS`. Image APFS yang sudah ada di workstation itu dipakai; tidak ada IPSW pengganti yang diunduh.

Yang terverifikasi:

- `docker compose up -d --build` berhasil; healthcheck container `healthy`; restart container memulihkan Xvfb dan VNC meski ada lock X11 lama.
- **9 regression test lolos** (setelah pengembangan dashboard: **12 test**, termasuk pemeriksaan field status baru dan ketahanan terhadap nilai env yang salah). Test memakai workspace sementara dan launcher palsu; tidak pernah menjalankan guest sungguhan.
- Test browser (Edge/Playwright): tidak ada error JavaScript, status RUNNING, tombol Start nonaktif saat berjalan, Stop aktif, noVNC tertanam terhubung.
- API live: durasi tidak valid → HTTP 422; start ganda → HTTP 409.
- Guest sungguhan mencapai Darwin/XNU, me-mount APFS, menyelesaikan 36 pemeriksaan init dengan nol kegagalan, menjalankan SpringBoard dan backboardd. Logo boot Apple terlihat lewat noVNC; backboardd mencatat event sentuh yang masuk (membuktikan jalur input, terpisah dari uji antarmuka interaktif penuh).
- **Boot 1 CPU mencapai Home Screen SpringBoard sungguhan** sekitar 38 menit setelah Start, dan Settings dibuka serta ter-render penuh beberapa menit kemudian. Startup aplikasi memakan waktu beberapa menit; widget yang putih dan input yang lambat adalah keterbatasan yang tersisa. Screenshot: `artifacts/dashboard-home.png`, `artifacts/dashboard-settings.png`.
- Image sistem diperiksa penuh dengan pembaca APFS Python independen: 62.261 entri, 12.429 checksum metadata terverifikasi, nol kegagalan; dua image (cache terkompresi vs tanpa kompresi) menghasilkan digest sensus yang sama.
- Uji stop otomatis lolos: sesi 60 detik berhenti sendiri dan tidak meninggalkan proses QEMU; sesi 1200 detik juga berhenti otomatis.

Yang **belum** terbukti / masih bermasalah:

- **Profil 4 CPU mengalami kernel panic** (ticket spinlock di `_pset0 + 0x100`, saat scheduling thread; pertama di `geod`, lalu di `fseventsd` setelah job latar dikurangi). Mengurangi service latar tidak memperbaikinya.
- **Profil 8 CPU baru preflight**: sekitar 14 menit, 8 CPU terdaftar, 36 init check lolos, `svc_test: 0 failed`, `surf_test: 80 checks, 0 failed`, tanpa panic — tetapi sesi preflight berakhir karena container diganti, dan ini **bukan** bukti Home Screen interaktif 8 CPU.
- Respons input end-to-end masih dalam pemeriksaan: backboardd mencatat timestamp input beberapa menit di belakang waktu pemrosesan saat boot 1 CPU sibuk.
- Rendering layar Home Screen/Settings **tidak** membuktikan kompatibilitas dengan setiap aplikasi. Tidak ada matriks kompatibilitas aplikasi yang diterbitkan.

Perbaikan yang tercatat selama validasi (sudah masuk ke kode/profil saat ini): memakai launcher `qemu/run-ios.sh` upstream beserta argumen durasi posisionalnya, path firmware AAVMF Ubuntu, penolakan file prasyarat yang hilang/kosong, pembersihan lock X11 saat start, desktop X11 portrait, staging runtime di volume Linux, buffering output serial, timer durasi + 40 detik, pelaporan `guest_status=failed` yang independen dari proses emulator, serta perbaikan input noVNC (hover lokal, throttle drag, lepas pointer saat blur). Perbaikan uji notifikasi (polling pengiriman dengan deadline 10 detik, dibangun ulang dari sumber) juga tercatat di sana.

## Keamanan dan batasan

Model keamanan proyek ini: **workstation lokal tepercaya milik satu pengguna**. Bukan desain yang diperkeras untuk hosting multi-pengguna.

- **Port hanya lokal.** Compose mem-publish `127.0.0.1:8000` dan `127.0.0.1:6080` saja. Jangan mem-publish port ini ke internet, jangan pasang reverse proxy publik tanpa autentikasi, dan jangan memakai lab ini dengan akun/data sensitif.
- **VNC tanpa autentikasi di dalam container.** `x11vnc` berjalan dengan `-nopw -localhost`; aksesnya hanya lewat UI web noVNC yang di-publish secara lokal. Kalau ada orang lain yang berbagi mesin yang sama, andalkan isolasi keamanan OS.
- **Jangan jalankan privileged dan jangan mount Docker socket.** Container memakai `security_opt: no-new-privileges:true`. Jangan mengubahnya.
- **Tidak ada akun Apple.** Proyek ini tidak bisa dan tidak bertujuan masuk ke akun Apple, mengunduh dari App Store, memakai seluler, atau menjalankan IPA secara umum.
- **Tidak ada image yang diunduh otomatis.** Pengguna mengontrol secara eksplisit pengunduhan dan pemrosesan IPSW. Jangan mendistribusikan ekstrak IPSW, image userland, atau file tanpa hak yang sesuai; baca ketentuan Apple.
- **State tidak persisten antar restart API.** Runtime state hidup di proses API; restart service tidak menempel kembali ke proses QEMU yang sudah berjalan.
- **Sumber daya tidak dibatasi per pengguna.** Tidak ada kuota, overlay per-VM, snapshot, autentikasi, RBAC, maupun audit di Fase 1. Itu semua masuk rencana Fase 2 dan tidak boleh diasumsikan sudah ada.

## Struktur proyek

```text
.
├── Dockerfile                  # Ubuntu 24.04: QEMU ARM64, AAVMF, SeaBIOS, Xvfb, x11vnc,
│                               # noVNC, websockify, 7zip; dependensi Python di /opt/wfs/.venv
├── compose.yaml                # Satu service wfs-ios-lab, volume qemu-runtime, healthcheck
├── .env.example                # Contoh konfigurasi (salin menjadi .env; .env tidak di-commit)
├── requirements.txt            # fastapi, uvicorn
├── requirements-dev.txt        # + httpx (untuk TestClient)
├── app/
│   ├── main.py                 # Manager FastAPI: status/start/stop/logs, deteksi panic
│   ├── launch.py               # Staging runtime Linux lalu exec launcher upstream
│   └── static/
│       ├── index.html          # Dashboard (tanpa dependensi luar)
│       └── vnc-cursor.css      # Kursor crosshair untuk noVNC (digabung ke base.css saat build)
├── scripts/
│   ├── bootstrap.sh            # Clone HakiOS di commit pin
│   ├── entrypoint.sh           # Xvfb + x11vnc + websockify + uvicorn
│   └── configure-novnc.py      # Patch rfb.js noVNC untuk input sentuh (gagal build kalau hook berubah)
├── tests/
│   ├── test_manager.py         # 12 regression test lifecycle manager (fixture terisolasi)
│   └── live_timeout.py         # Uji timeout sesi live (terpisah dari suite unit)
├── docs/
│   └── VALIDATION.md           # Hasil validasi terukur 31 Okt 2026 + bukti di artifacts/
├── artifacts/                  # Bukti validasi: screenshot, log boot, hasil test browser/API
└── workspace/                  # Bind mount persisten di host (hanya .gitkeep yang di-commit)
                                # Di Docker: sumber HakiOS ter-clone di workspace/hackios/
```

Yang sengaja tidak ada di repo (diabaikan `.gitignore`): checkout HakiOS (`hackios/`), image APFS hasil build, log sesi (`logs/`), virtualenv lokal (`.venv/`), dan file `.env`. Jangan pernah `git add` direktori-direktori itu — image-nya berukuran multi-GB.

## Pengembangan dan pengujian

Regression test memakai workspace sementara dan launcher palsu, sehingga aman dijalankan di Linux mana pun tanpa QEMU atau image iOS:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Cakupan test saat ini (12 test): prasyarat hilang, validasi durasi, start ganda + stop + restart + timer lama, shutdown menghentikan proses, home dan log kosong, error launcher, guest gagal, panic guest saat emulator masih hidup, staging image alternatif tanpa mengganti sumber, dashboard berbahasa Indonesia, field status baru, dan ketahanan status terhadap nilai env yang salah.

Hasil boot sungguhan **tidak** termasuk dalam suite unit; hasil itu dicatat terpisah di `docs/VALIDATION.md`. Uji timeout live ada di `tests/live_timeout.py` dan dijalankan terpisah karena membutuhkan proses API sungguhan dan waktu dinding nyata.

Konvensi yang dijaga di kode ini:

- Jangan menginterpolasi input pengguna ke shell. Launcher dijalankan lewat daftar argumen `subprocess.Popen`.
- Jangan mengubah perilaku API yang sudah dites tanpa memperbarui test. Field status baru harus aditif.
- Jangan mengklaim boot berhasil hanya karena container `healthy`. Buktinya adalah layar guest dan log boot, bukan healthcheck.
- Jangan meng-commit file besar hasil build. Kalau ragu, periksa `git status` sebelum commit.

## Rencana Fase 2

1. Pin dan verifikasi commit/checksum upstream; verifikasi kompatibilitas perintah dengan integration test.
2. Pisahkan API, worker VM, dan proxy WebSocket; tambah supervisi proses dan state persisten.
3. Pindah dari capture desktop Xvfb ke VNC/SPICE native QEMU; implementasikan API input dan screenshot yang deterministik.
4. Tambah overlay writable per-VM, snapshot, kuota, dan alokasi sumber daya yang dibatasi.
5. Tambah autentikasi, RBAC, audit, dan akses remote hanya lewat gateway TLS terautentikasi.
6. Validasi kompatibilitas aplikasi iOS dan terbitkan matriks kompatibilitas per aplikasi yang jujur.

## Sumber

- HakiOS (sumber kernel/userland/launcher): https://github.com/oosexgang/hakios-xnu-kernel
- Daftar file SeaBIOS (paket Ubuntu, termasuk `vgabios-ramfb.bin`): https://packages.ubuntu.com/noble/all/seabios/filelist
- Ketentuan hukum dan kepatuhan lisensi HakiOS: `LEGAL.md` dan `COMPLIANCE.md` di checkout HakiOS (`hackios/`, setelah bootstrap)
- Bukti validasi proyek ini: [docs/VALIDATION.md](docs/VALIDATION.md) dan `artifacts/`

---

*Perubahan terakhir (4 November 2026): dashboard ditulis ulang dalam bahasa Indonesia dengan countdown sesi, checklist prasyarat beserta perbaikannya, peringatan RAM, dan banner kernel panic; `/api/status` diperkaya dengan memori host, pemeriksaan kecocokan RAM, detail prasyarat, dan timing sesi; `.gitignore` mengabaikan checkout HakiOS, log, dan virtualenv. Identitas commit mengikuti identitas GitHub pemilik repo.*
