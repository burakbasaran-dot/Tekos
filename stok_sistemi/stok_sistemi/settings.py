"""
Geriye dönük uyumluluk: gerçek ayarlar proje kökündeki ``stok_sistemi.settings`` içindedir.

Eski bu dosya ``BASE_DIR`` olarak ``stok_sistemi/`` kullanıyordu; bu da kökteki
``db.sqlite3`` yerine yanlış konumdaki veritabanına işaret edebiliyordu ve
migration uygulanmış olsa bile "sütun yok" hatasına yol açıyordu.
"""

from stok_sistemi.settings import *  # noqa: F403, F401
