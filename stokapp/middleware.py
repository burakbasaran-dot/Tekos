"""
Hata loglama middleware'i - Error mesajlarını otomatik olarak HataLog'a kaydeder
"""
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin


class HataLogMiddleware(MiddlewareMixin):
    """Error mesajlarını HataLog modeline kaydeden middleware"""
    
    def process_response(self, request, response):
        """Response işlendikten sonra mesajları kontrol et"""
        try:
            from .models import HataLog
            
            # Mesajları al (sadece okumak için, silinmesin diye)
            storage = messages.get_messages(request)
            messages_to_log = []
            
            # Mesajları listeye kopyala
            for message in storage:
                if message.level_tag in ['error', 'warning']:
                    messages_to_log.append(message)
            
            # Mesajları logla
            for message in messages_to_log:
                try:
                    # Seviye belirleme
                    seviye_map = {
                        'error': 'ERROR',
                        'warning': 'WARNING',
                        'info': 'INFO',
                        'success': 'SUCCESS',
                    }
                    seviye = seviye_map.get(message.level_tag, 'ERROR')
                    
                    # View name al
                    view_name = 'unknown'
                    if hasattr(request, 'resolver_match') and request.resolver_match:
                        view_name = request.resolver_match.view_name or 'unknown'
                    
                    # HataLog kaydı oluştur
                    HataLog.objects.create(
                        mesaj=str(message.message)[:1000],  # Mesaj çok uzunsa kes
                        seviye=seviye,
                        kaynak=view_name,
                        kullanici=request.user if request.user.is_authenticated else None,
                        ip_adresi=self.get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    )
                except Exception:
                    # Hata loglama sırasında hata oluşursa sessizce geç
                    # Çünkü sonsuz döngü oluşabilir
                    pass
                    
        except ImportError:
            # HataLog modeli henüz migrate edilmemişse sessizce geç
            pass
        except Exception:
            # Herhangi bir hata durumunda sessizce geç
            pass
        
        return response
    
    def get_client_ip(self, request):
        """Client IP adresini al"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

