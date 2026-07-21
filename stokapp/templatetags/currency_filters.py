from django import template
from decimal import Decimal

register = template.Library()


@register.filter(name='tr_decimal')
def tr_decimal(value, places="2"):
    """
    Türkçe sayı formatı: binlik nokta (.), ondalık virgül (,).
    Örnek places=2: 1000000 -> 1.000.000,00
    places şablon içinde string verilir: {{ kur|tr_decimal:"4" }}
    """
    try:
        dec_places = int(str(places).strip())
        if dec_places < 0 or dec_places > 10:
            dec_places = 2
    except (ValueError, TypeError, AttributeError):
        dec_places = 2

    if value is None:
        return "0" + ("," + ("0" * dec_places) if dec_places > 0 else "")

    try:
        num = float(value)
    except (ValueError, TypeError, AttributeError):
        return "0" + ("," + ("0" * dec_places) if dec_places > 0 else "")

    is_negative = num < 0
    num = abs(num)
    formatted = f"{num:,.{dec_places}f}"
    parts = formatted.split(".")
    if len(parts) != 2:
        return "0" + ("," + ("0" * dec_places) if dec_places > 0 else "")
    integer_with_commas, decimal_part = parts[0], parts[1]
    integer_part = integer_with_commas.replace(",", ".")
    result = f"{integer_part},{decimal_part}"
    if is_negative:
        result = f"-{result}"
    return result


@register.filter(name='currency')
def currency(value):
    """
    Para birimini Türk Lirası formatına çevirir: 12.532,40
    Binlik ayırıcı: nokta (.)
    Ondalık ayırıcı: virgül (,)
    """
    if value is None:
        return "0,00"
    
    try:
        # Decimal veya float'ı string'e çevir
        if hasattr(value, '__float__'):
            num = float(value)
        else:
            num = float(str(value))
        
        # Negatif sayı kontrolü
        is_negative = num < 0
        num = abs(num)
        
        # İki ondalık basamakla formatla
        formatted = f"{num:,.2f}"
        
        # Nokta ve virgülü değiştir (binlik ayırıcı nokta, ondalık virgül)
        # Python format: 12532.40 -> "12,532.40"
        # İstediğimiz format: "12.532,40"
        parts = formatted.split('.')
        integer_part = parts[0].replace(',', '.')  # Binlik ayırıcıları nokta yap
        decimal_part = parts[1] if len(parts) > 1 else '00'
        
        result = f"{integer_part},{decimal_part}"
        
        # Negatif ise eksi işareti ekle
        if is_negative:
            result = f"-{result}"
        
        return result
    except (ValueError, TypeError, AttributeError):
        return "0,00"


@register.filter(name='format_adet')
def format_adet(value):
    """
    Adet (miktar) formatı:
    - Binlik ayırıcı: nokta (.)
    - Ondalık ayırıcı: virgül (,)
    - Ondalık basamak: 2 hane (sadece ondalık kısım varsa)
    - Tam sayı ise ondalık kısım gösterilmez
    Örnek: 1234 -> "1.234", 1234.56 -> "1.234,56"
    """
    if value is None:
        return "0"
    
    try:
        # Decimal'e çevir
        if isinstance(value, Decimal):
            num = value
        elif hasattr(value, '__float__'):
            num = Decimal(str(float(value)))
        else:
            num = Decimal(str(value))
        
        # Tam sayı kontrolü
        if num == num.quantize(Decimal('1')):
            # Tam sayı: ondalık kısım yok, sadece binlik ayırıcı
            formatted = f"{int(num):,}"
            formatted = formatted.replace(",", ".")
            return formatted
        else:
            # Ondalıklı sayı: 2 ondalık basamak
            formatted = f"{float(num):,.2f}"
            # Python format: 1234.56 -> "1,234.56"
            # İstediğimiz format: "1.234,56"
            parts = formatted.split('.')
            integer_part = parts[0].replace(',', '.')
            decimal_part = parts[1] if len(parts) > 1 else '00'
            return f"{integer_part},{decimal_part}"
    except (ValueError, TypeError, AttributeError):
        return str(value)
