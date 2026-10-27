import os
import requests

# API anahtarını çevre değişkeninden alıyoruz (Varsayılan olarak kendi anahtarınız ekli)
API_KEY = os.getenv("XRANKS_API_KEY")
DOMAIN_TO_CHECK = "nearadin.net"

url = "https://xranks.com/api/v1/domain/category"
headers = {"Authorization": API_KEY}
params = {"domain": DOMAIN_TO_CHECK}

try:
    response = requests.get(url, params=params, headers=headers)
    response.raise_for_status()  # HTTP hatalarını (404, 500 vb.) yakalar
    
    data = response.json()
    
    if "error" in data:
        raise Exception(f"API Hatası: {data['error']}")
        
    print(f"'{DOMAIN_TO_CHECK}' kategorisi:")
    print(data)

except requests.exceptions.RequestException as e:
    print(f"Bağlantı/İstek hatası oluştu: {e}")
except Exception as e:
    print(f"Hata: {e}")
