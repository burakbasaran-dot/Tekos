from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def format_decimal(value):
    """Tam sayıda ondalık gizler; ondalıklıysa gereksiz sıfırları siler (5.000→5, 5.500→5.5)."""
    if value is None or value == '':
        return value
    try:
        num = Decimal(str(value))
        if num == num.to_integral_value():
            return str(int(num))
        # En fazla 3 ondalık, trailing zero yok
        text = f"{num:.10f}".rstrip('0').rstrip('.')
        return text
    except (TypeError, ValueError, ArithmeticError):
        try:
            f = float(value)
            if f.is_integer():
                return str(int(f))
            return f"{f:.3f}".rstrip('0').rstrip('.')
        except (TypeError, ValueError):
            return value

@register.filter(name='format_miktar')
def format_miktar(value):
    """
    Miktar formatı: 
    - Tam sayı ise binlik ayraç ile tam sayı olarak göster (örn: 1.000)
    - Tam sayı değilse binlik ayraç ile virgülden sonra 2 hane göster (örn: 1.000,50)
    - Binlik ayraç: nokta (.)
    - Ondalık ayraç: virgül (,)
    """
    if value is None:
        return "0"
    
    try:
        # Decimal'i doğrudan kullan, daha hassas
        if isinstance(value, Decimal):
            num = value
        elif hasattr(value, '__float__'):
            num = Decimal(str(value))
        else:
            num = Decimal(str(value))
        
        # Negatif sayı kontrolü
        is_negative = num < 0
        num = abs(num)
        
        # Tam sayı mı kontrol et (Decimal için)
        if num % 1 == 0:
            # Tam sayı: binlik ayraç ile formatla
            int_num = int(num)
            formatted = f"{int_num:,}".replace(',', '.')
            return f"-{formatted}" if is_negative else formatted
        else:
            # Ondalıklı: virgülden sonra 2 hane, binlik ayraç nokta
            formatted = f"{num:,.2f}"
            # Python format: 12532.40 -> "12,532.40"
            # İstediğimiz format: "12.532,40"
            parts = formatted.split('.')
            integer_part = parts[0].replace(',', '.')  # Binlik ayırıcıları nokta yap
            decimal_part = parts[1] if len(parts) > 1 else '00'
            
            result = f"{integer_part},{decimal_part}"
            return f"-{result}" if is_negative else result
            
    except (ValueError, TypeError, AttributeError):
        return "0"


@register.filter(name='format_stok_miktar')
def format_stok_miktar(value):
    """
    Stok listesi miktar formatı:
    - Tam sayıysa ondalık göstermez (örn: 12)
    - Ondalıklıysa noktadan sonra 2 basamak gösterir (örn: 12.50)
    """
    if value is None:
        return "0"
    try:
        num = Decimal(str(value))
        if num % 1 == 0:
            return str(int(num))
        return f"{num:.2f}"
    except (ValueError, TypeError, AttributeError):
        return "0"