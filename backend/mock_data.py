"""
Generator data mock realistis untuk mode `mock` (default, tanpa API key apa pun).

Data dibuat deterministik berdasarkan seed dari (lokasi + kategori) agar hasil terasa
konsisten untuk input yang sama, tapi tetap bervariasi antar lokasi/kategori berbeda.
"""
import random
from typing import Dict, List

from .schemas import KompetitorRaw, UlasanMentah

# ---------------------------------------------------------------------------
# Nama usaha per kategori (dipakai untuk generate nama kompetitor)
# ---------------------------------------------------------------------------

NAMA_POOL: Dict[str, List[str]] = {
    "coffee shop": [
        "Kopi Senja", "Warkop Bintang Timur", "Filosofi Kopi Corner", "Kopi Kenangan Lama",
        "Ruang Seduh", "Kopi Manual Brew", "Kedai Kopi Djaman Doeloe", "Titik Kumpul Coffee",
        "Kopi Anak Bangsa", "Selasar Kopi & Roti",
    ],
    "restoran": [
        "Warung Nasi Ibu Tuti", "RM Sederhana Berkah", "Dapur Nusantara", "Bebek Goreng H. Slamet",
        "Ayam Bakar Mas Bro", "Sate Klathak Pak Pong", "Soto Betawi Bang Udin", "Nasi Goreng Gerobak Mas",
        "Pondok Lesehan Asri", "Waroeng Steak Rakyat",
    ],
    "salon": [
        "Salon Cantik Elok", "Barbershop Gagah Pria", "Salon Muslimah Anggun", "Studio Rambut Kreasi",
        "Salon & Spa Bunga Melati", "Gentleman's Cut", "Salon Kecantikan Ratu", "Glow Beauty Studio",
        "Salon Modern Look", "Salon Keluarga Ceria",
    ],
    "bengkel": [
        "Bengkel Jaya Motor", "Bengkel Resmi Auto Sejahtera", "Bengkel Berkah Teknik", "Bengkel Cepat Selesai",
        "Bengkel Sinar Motor", "Bengkel Mobil Prima", "Bengkel Ban & Kaki-Kaki Makmur", "Bengkel Las & Body Repair Jujur",
        "Bengkel Motor Listrik Maju", "Bengkel 24 Jam Siaga",
    ],
    "klinik": [
        "Klinik Sehat Sentosa", "Klinik Pratama Keluarga", "Klinik Gigi Senyum Ceria", "Klinik Kecantikan Estetika",
        "Klinik Umum 24 Jam Waras", "Klinik Anak Tumbuh Sehat", "Klinik Fisioterapi Bugar", "Klinik Herbal Alami",
        "Klinik Vaksinasi Prima", "Klinik Bersalin Ibu & Anak",
    ],
}

ALAMAT_JALAN = [
    "Jl. Merdeka", "Jl. Sudirman", "Jl. Diponegoro", "Jl. Gatot Subroto", "Jl. Ahmad Yani",
    "Jl. Veteran", "Jl. Cihampelas", "Jl. Braga", "Jl. Malioboro Kecil", "Jl. Pandanaran",
]

# ---------------------------------------------------------------------------
# Template ulasan per kategori: (teks, rating, tema_dominan)
# Campuran positif / negatif / netral supaya Agent 2 punya variasi untuk diklasifikasi.
# ---------------------------------------------------------------------------

ULASAN_TEMPLATE: Dict[str, List[tuple]] = {
    "coffee shop": [
        ("Kopinya enak banget, racikan baristanya juara. Bakal balik lagi!", 5),
        ("Tempatnya nyaman buat kerja, wifi kencang dan colokan banyak.", 5),
        ("Harga agak mahal untuk ukuran kantong mahasiswa, tapi rasa sepadan.", 3),
        ("Pelayanannya lambat banget pas weekend, nunggu kopi 30 menit.", 2),
        ("Parkirannya sempit, susah kalau bawa mobil pas jam ramai.", 2),
        ("Suasana cozy, cocok buat nongkrong santai sama teman.", 4),
        ("Kebersihan meja dan toilet terjaga, pelayan ramah-ramah.", 5),
        ("Menu kopinya itu-itu saja, kurang variasi dibanding kompetitor.", 3),
        ("Harga terjangkau untuk kualitas kopi yang cukup baik.", 4),
        ("Lokasinya strategis banget, dekat kampus dan gampang dijangkau.", 5),
        ("Antrian panjang dan kasir cuma satu, kurang efisien.", 2),
        ("Baristanya kurang ramah, agak jutek waktu ditanya menu.", 2),
    ],
    "restoran": [
        ("Rasanya otentik banget, mengingatkan masakan rumah.", 5),
        ("Porsinya besar, harganya masih masuk akal buat keluarga.", 5),
        ("Pelayanan agak lama, mungkin karena selalu ramai pengunjung.", 3),
        ("Tempat makan kurang bersih, ada meja yang belum dilap.", 2),
        ("Parkir luas dan mudah, cocok buat bawa keluarga besar.", 5),
        ("Rasa masakannya biasa saja, tidak seistimewa yang diharapkan.", 3),
        ("Harga sedikit mahal untuk porsi yang diberikan.", 2),
        ("Pelayan sangat ramah dan cepat tanggap saat dipanggil.", 5),
        ("Dapur terlihat kurang higienis dari meja pelanggan.", 2),
        ("Menu bervariasi dan selalu ada menu spesial tiap minggu.", 4),
        ("Tempatnya sempit dan panas, AC kurang dingin.", 2),
        ("Sambelnya juara, bikin nagih pengen balik lagi.", 5),
    ],
    "salon": [
        ("Hasil potongan rapi dan sesuai permintaan, puas banget.", 5),
        ("Harganya terjangkau untuk hasil yang berkualitas.", 4),
        ("Nunggu lama walau sudah booking duluan.", 2),
        ("Kapster sangat komunikatif dan sabar dengerin request.", 5),
        ("Tempatnya kurang bersih, banyak rambut berserakan di lantai.", 2),
        ("Parkir motor susah karena di pinggir jalan ramai.", 3),
        ("Produk perawatan yang dipakai berkualitas, hasil maksimal.", 5),
        ("Harga agak mahal dibanding salon lain di sekitar sini.", 3),
        ("Pelayanannya ramah dari resepsionis sampai kapster.", 5),
        ("Alat-alat terlihat sudah lama tidak diganti, kurang higienis.", 2),
        ("Lokasi strategis di pinggir jalan utama, gampang ditemukan.", 4),
        ("Hasil rambut kurang sesuai ekspektasi, agak kecewa.", 2),
    ],
    "bengkel": [
        ("Servisnya cepat dan montirnya sangat berpengalaman.", 5),
        ("Harga spare part lumayan mahal dibanding bengkel lain.", 3),
        ("Antri lama walau sudah janjian dari pagi.", 2),
        ("Mekaniknya jujur, kasih tau kerusakan apa adanya.", 5),
        ("Tempatnya berantakan dan agak kotor, oli tercecer di lantai.", 2),
        ("Parkir kendaraan yang antri servis cukup luas.", 4),
        ("Hasil servis awet, motor jadi enak dipakai lagi.", 5),
        ("Harga cukup terjangkau untuk kualitas servis yang diberikan.", 4),
        ("Pelayanan kurang ramah, montir jarang menjelaskan detail.", 2),
        ("Lokasi agak susah dicari karena masuk gang kecil.", 3),
        ("Peralatan bengkel lengkap dan modern.", 5),
        ("Estimasi waktu servis sering meleset jauh dari janji.", 2),
    ],
    "klinik": [
        ("Dokternya ramah dan menjelaskan dengan detail.", 5),
        ("Antrian cukup lama meski sudah pakai sistem booking online.", 2),
        ("Biaya konsultasi terjangkau dibanding klinik sekitar.", 4),
        ("Ruang tunggu bersih dan nyaman, ada AC dan air minum.", 5),
        ("Parkir kendaraan terbatas, sering penuh di jam sibuk.", 2),
        ("Perawat sangat sigap dan komunikatif ke pasien.", 5),
        ("Harga obat di apotek klinik lebih mahal dari luar.", 3),
        ("Kebersihan ruang periksa sangat terjaga, alat-alat steril.", 5),
        ("Pelayanan pendaftaran agak lambat dan kurang terorganisir.", 2),
        ("Lokasi strategis dan mudah diakses kendaraan umum.", 4),
        ("Dokter spesialis jarang ada di tempat sesuai jadwal.", 2),
        ("Fasilitas lengkap untuk ukuran klinik pratama.", 4),
    ],
}

HARGA_RANGE: Dict[str, List[str]] = {
    "coffee shop": ["Rp15.000 - Rp35.000", "Rp18.000 - Rp45.000", "Rp10.000 - Rp28.000", "Rp20.000 - Rp50.000"],
    "restoran": ["Rp15.000 - Rp40.000", "Rp25.000 - Rp75.000", "Rp10.000 - Rp30.000", "Rp30.000 - Rp90.000"],
    "salon": ["Rp25.000 - Rp100.000", "Rp50.000 - Rp250.000", "Rp20.000 - Rp75.000", "Rp75.000 - Rp350.000"],
    "bengkel": ["Rp50.000 - Rp300.000", "Rp100.000 - Rp750.000", "Rp30.000 - Rp150.000", "Rp150.000 - Rp1.000.000"],
    "klinik": ["Rp50.000 - Rp150.000", "Rp100.000 - Rp350.000", "Rp75.000 - Rp250.000", "Rp150.000 - Rp500.000"],
}


def generate_mock_kompetitor(lokasi: str, kategori: str, top_n: int) -> List[KompetitorRaw]:
    """Hasilkan daftar kompetitor mock realistis lengkap dengan ulasan sampel."""
    seed_str = f"{lokasi.strip().lower()}::{kategori}"
    rng = random.Random(seed_str)

    nama_pool = NAMA_POOL.get(kategori, NAMA_POOL["coffee shop"])
    ulasan_pool = ULASAN_TEMPLATE.get(kategori, ULASAN_TEMPLATE["coffee shop"])
    harga_pool = HARGA_RANGE.get(kategori, HARGA_RANGE["coffee shop"])

    nama_terpilih = nama_pool[: max(top_n, 5)]
    rng.shuffle(nama_terpilih)

    kompetitor_list: List[KompetitorRaw] = []
    for i, nama in enumerate(nama_terpilih[:top_n]):
        rating = round(rng.uniform(3.4, 4.9), 1)
        jumlah_review = rng.randint(35, 890)
        jalan = rng.choice(ALAMAT_JALAN)
        alamat = f"{jalan} No. {rng.randint(1, 150)}, {lokasi.strip().title()}"
        harga = rng.choice(harga_pool)

        jumlah_ulasan = rng.randint(4, 5)
        sample_ulasan = rng.sample(ulasan_pool, k=min(jumlah_ulasan, len(ulasan_pool)))
        penulis_pool = [
            "Andi S.", "Rina W.", "Budi P.", "Siti A.", "Dewi K.", "Fajar N.",
            "Maya L.", "Rian T.", "Putri H.", "Agus D.",
        ]
        ulasan_objs = [
            UlasanMentah(teks=teks, rating=rating_ulasan, penulis=rng.choice(penulis_pool))
            for teks, rating_ulasan in sample_ulasan
        ]

        kompetitor_list.append(
            KompetitorRaw(
                nama=nama,
                alamat=alamat,
                rating=rating,
                jumlah_review=jumlah_review,
                rentang_harga=harga,
                ulasan=ulasan_objs,
            )
        )

    return kompetitor_list
