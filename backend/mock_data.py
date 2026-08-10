"""
Generator data mock realistis untuk mode `mock` (default, tanpa API key apa pun).

Data dibuat deterministik berdasarkan seed dari (lokasi + kategori) agar hasil terasa
konsisten untuk input yang sama, tapi tetap bervariasi antar lokasi/kategori berbeda.
"""
import math
import random
from typing import Dict, List, Tuple

from .schemas import KompetitorRaw, UlasanMentah

# ---------------------------------------------------------------------------
# Koordinat pusat kota untuk keperluan visualisasi peta (sintetis, bukan geocoding
# sungguhan). Dicocokkan lewat substring pada nama lokasi; fallback ke titik acak
# deterministik di sekitar Pulau Jawa jika kota tidak dikenali.
# ---------------------------------------------------------------------------

KOTA_KNOWN: Dict[str, Tuple[float, float]] = {
    "jakarta": (-6.2088, 106.8456),
    "bandung": (-6.9175, 107.6191),
    "surabaya": (-7.2575, 112.7521),
    "yogyakarta": (-7.7956, 110.3695),
    "jogja": (-7.7956, 110.3695),
    "malang": (-7.9666, 112.6326),
    "semarang": (-6.9932, 110.4203),
    "medan": (3.5952, 98.6722),
    "makassar": (-5.1477, 119.4327),
    "denpasar": (-8.6705, 115.2126),
    "bali": (-8.4095, 115.1889),
    "bogor": (-6.5971, 106.8060),
    "depok": (-6.4025, 106.7942),
    "bekasi": (-6.2383, 106.9756),
    "tangerang": (-6.1783, 106.6319),
    "solo": (-7.5755, 110.8243),
    "surakarta": (-7.5755, 110.8243),
    "palembang": (-2.9761, 104.7754),
    "balikpapan": (-1.2379, 116.8529),
    "padang": (-0.9471, 100.4172),
    "manado": (1.4748, 124.8421),
}

JAVA_BBOX = {"lat_min": -8.2, "lat_max": -6.0, "lng_min": 106.0, "lng_max": 114.5}


def _titik_pusat(lokasi: str, rng: random.Random) -> Tuple[float, float]:
    lokasi_lower = lokasi.strip().lower()
    for kota, koordinat in KOTA_KNOWN.items():
        if kota in lokasi_lower:
            # Sedikit jitter supaya tidak selalu persis di titik yang sama.
            jitter = 0.01
            return (koordinat[0] + rng.uniform(-jitter, jitter), koordinat[1] + rng.uniform(-jitter, jitter))
    return (
        rng.uniform(JAVA_BBOX["lat_min"], JAVA_BBOX["lat_max"]),
        rng.uniform(JAVA_BBOX["lng_min"], JAVA_BBOX["lng_max"]),
    )


ARAH_MATA_ANGIN = ["utara", "timur laut", "timur", "tenggara", "selatan", "barat daya", "barat", "barat laut"]


def _arah_dari_sudut(sudut_rad: float) -> str:
    derajat = math.degrees(sudut_rad) % 360
    return ARAH_MATA_ANGIN[int((derajat + 22.5) // 45) % 8]


def _titik_sekitar(
    pusat_lat: float, pusat_lng: float, radius_km: float, rng: random.Random
) -> Tuple[float, float, float, str]:
    """Sebar titik acak di dalam lingkaran radius_km dari titik pusat (proyeksi datar sederhana).

    Mengembalikan (lat, lng, jarak_km, arah_mata_angin) — jarak & arah dipakai lagi untuk
    menyusun teks alamat supaya KONSISTEN dengan posisi titik di peta (bukan dua hal acak
    yang independen, yang sebelumnya bikin alamat teks tidak nyambung dengan pin di peta).
    """
    sudut = rng.uniform(0, 2 * math.pi)
    jarak_km = rng.uniform(0.15, radius_km)
    dlat = (jarak_km * math.cos(sudut)) / 111.0
    dlng = (jarak_km * math.sin(sudut)) / (111.0 * math.cos(math.radians(pusat_lat)) or 1)
    return (pusat_lat + dlat, pusat_lng + dlng, jarak_km, _arah_dari_sudut(sudut))

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
    "laundry": [
        "Laundry Kilat Bersih", "Wangi Laundry & Dry Clean", "Laundry Sultan", "Rapi Laundry Express",
        "Laundry Ceria 24 Jam", "Bersih Elektrik Laundry", "Laundry Hemat Kilo", "Laundry Premium Wash",
        "Sinar Laundry", "Laundry Kita Bersama",
    ],
    "apotek": [
        "Apotek Sehat Selalu", "Apotek Keluarga Waras", "Apotek K-24 Mandiri", "Apotek Cahaya Farma",
        "Apotek Bahagia Sentosa", "Apotek Amanah Farma", "Apotek Sumber Sehat", "Apotek Griya Medika",
        "Apotek Berkah Farma", "Apotek Prima Husada",
    ],
    "minimarket": [
        "Minimarket Berkah Jaya", "Toko Serba Ada Makmur", "Minimarket 24 Jam Sejahtera", "Warung Modern Bahagia",
        "Minimarket Sumber Rejeki", "Toko Kelontong Barokah", "Minimarket Cepat Saji", "Toko Sembako Aman",
        "Minimarket Keluarga Hemat", "Toko Grosir Untung",
    ],
    "gym": [
        "Gym Otot Kuat Fitness", "Fit Zone Gym & Yoga", "Gym Sehat Bugar", "Powerhouse Gym Center",
        "Gym Semangat Baru", "Fitness First Local", "Gym Kekar Perkasa", "Titik Bugar Fitness Studio",
        "Gym Energi Muda", "Gym Sentosa Fit",
    ],
    "toko fashion": [
        "Toko Fashion Trendy Style", "Butik Anggun Modis", "Toko Baju Kekinian", "Fashion Hub Casual Wear",
        "Toko Pakaian Gaya Muda", "Butik Elegan Nusantara", "Toko Fashion Streetwear", "Toko Baju Muslimah Syar'i",
        "Fashion Corner Outlet", "Toko Baju Anak & Dewasa",
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
    "laundry": [
        ("Hasil cucian wangi dan rapi, disetrika juga rapi.", 5),
        ("Harga per kilo murah, cocok buat anak kos.", 5),
        ("Pelayanannya ramah, selalu tepat waktu sesuai janji.", 5),
        ("Baju sering ketuker sama punya orang lain, agak repot.", 2),
        ("Tempatnya bersih dan wangi, nyaman nunggu di sana.", 5),
        ("Kadang ada baju yang luntur, kurang hati-hati milah warna.", 2),
        ("Parkir motor gampang di depan toko.", 4),
        ("Antrian lama pas weekend, banyak yang nitip cucian.", 2),
        ("Harga sedikit mahal dibanding laundry lain di sekitar sini.", 3),
        ("Lokasinya strategis, dekat kampus jadi gampang dijangkau.", 5),
        ("Hasil setrikaan kurang rapi, masih ada yang kusut.", 2),
        ("Pelayanan cepat, cucian selesai dalam sehari.", 4),
    ],
    "apotek": [
        ("Obatnya lengkap, jarang kehabisan stok.", 5),
        ("Harganya lebih murah dibanding apotek chain lain.", 4),
        ("Apotekernya ramah dan mau jelasin dosis dengan sabar.", 5),
        ("Antrian panjang terutama pas jam pulang kerja.", 2),
        ("Tempatnya bersih dan tertata rapi, nyaman menunggu.", 5),
        ("Harga obat lumayan mahal untuk beberapa jenis.", 3),
        ("Parkir motor terbatas, kadang penuh.", 2),
        ("Buka 24 jam jadi sangat membantu saat darurat malam.", 5),
        ("Pelayanan kasir agak lambat, cuma satu orang yang jaga.", 2),
        ("Lokasi strategis, dekat dengan klinik dan rumah sakit.", 5),
        ("Stok obat resep kadang kosong, harus pesan dulu.", 3),
        ("Staf kurang informatif soal efek samping obat.", 2),
    ],
    "minimarket": [
        ("Barangnya lengkap, jarang kehabisan stok kebutuhan harian.", 5),
        ("Harga cukup bersaing dibanding minimarket sebelah.", 4),
        ("Kasirnya ramah dan cepat, jarang antri lama.", 5),
        ("Tempatnya agak sempit dan berantakan, susah cari barang.", 2),
        ("Kebersihan terjaga, rak-raknya rapi dan bersih.", 5),
        ("Harga beberapa barang lebih mahal dari toko lain.", 3),
        ("Parkir motor luas dan gampang.", 4),
        ("Antrian kasir panjang pas jam pulang kerja.", 2),
        ("Lokasinya strategis di pinggir jalan besar.", 5),
        ("Karyawannya kurang ramah, jarang senyum.", 2),
        ("Stok barang promo cepat habis, kadang kecewa.", 3),
        ("Buka 24 jam sangat membantu buat belanja mendadak.", 5),
    ],
    "gym": [
        ("Alat-alatnya lengkap dan terawat dengan baik.", 5),
        ("Harga membership terjangkau untuk fasilitas yang didapat.", 4),
        ("Trainer-nya ramah dan siap membantu kalau ditanya.", 5),
        ("Tempatnya kurang bersih, alat suka penuh keringat orang lain.", 2),
        ("Ruangan ber-AC dan nyaman untuk latihan lama.", 5),
        ("Membership agak mahal dibanding gym lain di sekitar.", 3),
        ("Parkir kendaraan sempit banget pas jam ramai.", 2),
        ("Lokasi strategis, gampang dijangkau dari kampus.", 5),
        ("Antrian alat panjang pas jam sibuk sore hari.", 2),
        ("Fasilitas loker dan kamar mandi kurang terawat.", 2),
        ("Suasana gym semangat, banyak yang termotivasi latihan.", 4),
        ("Kelas grup seperti zumba dan yoga seru dan variatif.", 5),
    ],
    "toko fashion": [
        ("Modelnya kekinian dan selalu update sama tren terbaru.", 5),
        ("Harga terjangkau untuk kualitas bahan yang lumayan bagus.", 4),
        ("Pelayanan ramah, mau bantu carikan ukuran yang pas.", 5),
        ("Bahannya tipis dan kurang awet, agak kecewa.", 2),
        ("Tokonya rapi dan bersih, enak buat lihat-lihat baju.", 5),
        ("Harga agak mahal untuk kualitas yang biasa saja.", 3),
        ("Parkir susah karena di area pertokoan yang padat.", 2),
        ("Lokasinya strategis di pusat perbelanjaan.", 5),
        ("Stok ukuran sering kosong buat yang XL ke atas.", 3),
        ("Pegawai kurang ramah, jarang menyapa pengunjung.", 2),
        ("Banyak pilihan model dan warna, betah belanja lama.", 5),
        ("Kualitas jahitan rapi dan tidak gampang lepas.", 4),
    ],
}

HARGA_RANGE: Dict[str, List[str]] = {
    "coffee shop": ["Rp15.000 - Rp35.000", "Rp18.000 - Rp45.000", "Rp10.000 - Rp28.000", "Rp20.000 - Rp50.000"],
    "restoran": ["Rp15.000 - Rp40.000", "Rp25.000 - Rp75.000", "Rp10.000 - Rp30.000", "Rp30.000 - Rp90.000"],
    "salon": ["Rp25.000 - Rp100.000", "Rp50.000 - Rp250.000", "Rp20.000 - Rp75.000", "Rp75.000 - Rp350.000"],
    "bengkel": ["Rp50.000 - Rp300.000", "Rp100.000 - Rp750.000", "Rp30.000 - Rp150.000", "Rp150.000 - Rp1.000.000"],
    "klinik": ["Rp50.000 - Rp150.000", "Rp100.000 - Rp350.000", "Rp75.000 - Rp250.000", "Rp150.000 - Rp500.000"],
    "laundry": ["Rp4.000 - Rp8.000/kg", "Rp5.000 - Rp10.000/kg", "Rp7.000 - Rp15.000/kg", "Rp8.000 - Rp20.000/kg"],
    "apotek": ["Rp5.000 - Rp50.000", "Rp10.000 - Rp150.000", "Rp15.000 - Rp100.000", "Rp20.000 - Rp250.000"],
    "minimarket": ["Rp1.000 - Rp30.000", "Rp2.000 - Rp50.000", "Rp3.000 - Rp75.000", "Rp5.000 - Rp100.000"],
    "gym": ["Rp100.000 - Rp250.000/bulan", "Rp150.000 - Rp400.000/bulan", "Rp300.000 - Rp750.000/bulan", "Rp400.000 - Rp1.000.000/bulan"],
    "toko fashion": ["Rp30.000 - Rp100.000", "Rp50.000 - Rp150.000", "Rp75.000 - Rp300.000", "Rp150.000 - Rp500.000"],
}


def generate_mock_kompetitor(
    lokasi: str, kategori: str, top_n: int, radius_km: float = 2.0
) -> Tuple[List[KompetitorRaw], float, float]:
    """Hasilkan daftar kompetitor mock realistis lengkap dengan ulasan sampel & koordinat peta.

    Mengembalikan (daftar_kompetitor, pusat_lat, pusat_lng).
    """
    seed_str = f"{lokasi.strip().lower()}::{kategori}"
    rng = random.Random(seed_str)

    pusat_lat, pusat_lng = _titik_pusat(lokasi, rng)

    nama_pool = NAMA_POOL.get(kategori, NAMA_POOL["coffee shop"])
    ulasan_pool = ULASAN_TEMPLATE.get(kategori, ULASAN_TEMPLATE["coffee shop"])
    harga_pool = HARGA_RANGE.get(kategori, HARGA_RANGE["coffee shop"])

    nama_terpilih = nama_pool[: max(top_n, 5)]
    rng.shuffle(nama_terpilih)

    kompetitor_list: List[KompetitorRaw] = []
    for i, nama in enumerate(nama_terpilih[:top_n]):
        rating = round(rng.uniform(3.4, 4.9), 1)
        jumlah_review = rng.randint(35, 890)
        harga = rng.choice(harga_pool)
        lat, lng, jarak_km, arah = _titik_sekitar(pusat_lat, pusat_lng, radius_km, rng)
        jalan = rng.choice(ALAMAT_JALAN)
        # Alamat dibangun dari jarak & arah yang SAMA dipakai untuk koordinat peta,
        # supaya teksnya konsisten dengan posisi pin (bukan nama jalan acak yang tidak
        # berkaitan dengan lat/lng, yang sebelumnya bisa 'meleset' dari peta sungguhan).
        alamat = f"Sekitar {jalan}, ±{jarak_km:.1f} km {arah} dari pusat {lokasi.strip().title()}"

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
                lat=round(lat, 6),
                lng=round(lng, 6),
            )
        )

    return kompetitor_list, round(pusat_lat, 6), round(pusat_lng, 6)
