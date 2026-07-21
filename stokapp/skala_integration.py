"""
Skala Suite MRP entegrasyon modülü
Skala Suite'den stok, cari ve reçete verilerini çeker
"""
try:
    import requests
    from bs4 import BeautifulSoup
    import pandas as pd
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None
    BeautifulSoup = None
    pd = None

from io import BytesIO
import time
from django.conf import settings


class SkalaSuiteIntegration:
    """
    Skala Suite MRP sisteminden veri çekmek için entegrasyon sınıfı
    """
    BASE_URL = "https://mrp.skalasuite.com"
    LOGIN_URL = f"{BASE_URL}/login"
    
    def __init__(self, email, password):
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests modülü yüklü değil. Lütfen 'pip install requests' komutunu çalıştırın.")
        
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.is_authenticated = False
    
    def login(self):
        """
        Skala Suite'e giriş yap
        """
        try:
            # Login sayfasını al
            response = self.session.get(self.LOGIN_URL)
            response.raise_for_status()
            
            # HTML'den CSRF token ve form bilgilerini çıkar
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Login formunu bul
            # Form alanlarını bul (gerçek form yapısına göre düzenlenmeli)
            login_data = {
                'email': self.email,
                'password': self.password,
            }
            
            # CSRF token varsa ekle
            csrf_token = soup.find('input', {'name': 'csrf_token'}) or soup.find('input', {'name': '_token'})
            if csrf_token:
                login_data[csrf_token.get('name')] = csrf_token.get('value')
            
            # Login POST isteği
            response = self.session.post(self.LOGIN_URL, data=login_data, allow_redirects=False)
            
            # Başarılı giriş kontrolü
            if response.status_code in [200, 302]:
                # Dashboard'a yönlendirildiyse veya başarılı olduysa
                self.is_authenticated = True
                return True
            
            return False
            
        except Exception as e:
            print(f"Login hatası: {str(e)}")
            return False
    
    def fetch_stock_data(self):
        """
        Stok verilerini çek
        """
        if not self.is_authenticated:
            if not self.login():
                return None
        
        try:
            # Stok listesi sayfasına git (gerçek URL'yi kontrol et)
            stock_url = f"{self.BASE_URL}/stocks"  # veya "/stok" veya "/urunler" gibi
            response = self.session.get(stock_url)
            response.raise_for_status()
            
            # HTML'den tablo verilerini çıkar
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tablo yapısına göre verileri parse et
            stock_data = []
            table = soup.find('table')  # Tablo yapısına göre düzenlenmeli
            
            if table:
                rows = table.find_all('tr')[1:]  # Header'ı atla
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) > 0:
                        stock_data.append({
                            'Stok Kodu': cols[0].text.strip() if len(cols) > 0 else '',
                            'Ürün Adı': cols[1].text.strip() if len(cols) > 1 else '',
                            'Kategori': cols[2].text.strip() if len(cols) > 2 else '',
                            'Birim': cols[3].text.strip() if len(cols) > 3 else 'Adet',
                            'Mevcut Miktar': cols[4].text.strip() if len(cols) > 4 else '0',
                            'Minimum Stok': cols[5].text.strip() if len(cols) > 5 else '0',
                            'Alış Fiyatı': cols[6].text.strip() if len(cols) > 6 else '0',
                            'Para Birimi': cols[7].text.strip() if len(cols) > 7 else 'TL',
                            'Barkod': cols[8].text.strip() if len(cols) > 8 else '',
                            'Açıklama': cols[9].text.strip() if len(cols) > 9 else '',
                        })
            
            return pd.DataFrame(stock_data) if stock_data else pd.DataFrame()
            
        except Exception as e:
            print(f"Stok verisi çekme hatası: {str(e)}")
            return None
    
    def fetch_cari_data(self):
        """
        Cari (müşteri/tedarikçi) verilerini çek
        """
        if not self.is_authenticated:
            if not self.login():
                return None
        
        try:
            # Cari listesi sayfasına git (gerçek URL'yi kontrol et)
            cari_url = f"{self.BASE_URL}/customers"  # veya "/cari" veya "/musteriler" gibi
            response = self.session.get(cari_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            cari_data = []
            table = soup.find('table')
            
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) > 0:
                        cari_data.append({
                            'Ad': cols[0].text.strip() if len(cols) > 0 else '',
                            'Telefon': cols[1].text.strip() if len(cols) > 1 else '',
                            'E-posta': cols[2].text.strip() if len(cols) > 2 else '',
                            'Adres': cols[3].text.strip() if len(cols) > 3 else '',
                        })
            
            return pd.DataFrame(cari_data) if cari_data else pd.DataFrame()
            
        except Exception as e:
            print(f"Cari verisi çekme hatası: {str(e)}")
            return None
    
    def fetch_recete_data(self):
        """
        Reçete verilerini çek
        """
        if not self.is_authenticated:
            if not self.login():
                return None
        
        try:
            # Reçete listesi sayfasına git (gerçek URL'yi kontrol et)
            recete_url = f"{self.BASE_URL}/recipes"  # veya "/recete" veya "/recepteler" gibi
            response = self.session.get(recete_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            recete_data = []
            # Reçete yapısına göre parse et
            table = soup.find('table')
            
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) > 0:
                        recete_data.append({
                            'Reçete Kodu': cols[0].text.strip() if len(cols) > 0 else '',
                            'Reçete Adı': cols[1].text.strip() if len(cols) > 1 else '',
                            'Açıklama': cols[2].text.strip() if len(cols) > 2 else '',
                        })
            
            return pd.DataFrame(recete_data) if recete_data else pd.DataFrame()
            
        except Exception as e:
            print(f"Reçete verisi çekme hatası: {str(e)}")
            return None
    
    def export_to_excel(self, stock_df=None, cari_df=None, recete_df=None):
        """
        Verileri Excel formatına dönüştür
        """
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if stock_df is not None and not stock_df.empty:
                stock_df.to_excel(writer, sheet_name='Stok', index=False)
            
            if cari_df is not None and not cari_df.empty:
                cari_df.to_excel(writer, sheet_name='Cari', index=False)
            
            if recete_df is not None and not recete_df.empty:
                recete_df.to_excel(writer, sheet_name='Reçete', index=False)
        
        output.seek(0)
        return output

