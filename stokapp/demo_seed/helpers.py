"""Yardımcılar — demo sunum verisi doldurma."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

User = get_user_model()

DEMO_MARKER = 'DEMO'
PDF_BYTES = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
178
%%EOF"""


def demo_pdf(name: str = 'demo.pdf') -> ContentFile:
    return ContentFile(PDF_BYTES, name=name)


def demo_nc(name: str = 'demo.nc') -> ContentFile:
    content = b'; TEKOS demo CNC program\nG00 X0 Y0\nM30\n'
    return ContentFile(content, name=name)


def get_seed_user():
    user = User.objects.filter(is_superuser=True).order_by('pk').first()
    if user:
        return user
    user = User.objects.filter(username='admin').first()
    if user:
        return user
    return User.objects.order_by('pk').first()


def d(days_ago: int = 0) -> date:
    return date.today() - timedelta(days=days_ago)


def dt(days_ago: int = 0, hour: int = 9) -> datetime:
    return timezone.make_aware(
        datetime.combine(d(days_ago), datetime.min.time().replace(hour=hour))
    )


def money(low: float, high: float) -> Decimal:
    return Decimal(str(round(random.uniform(low, high), 2)))


def pick(items):
    return random.choice(items)


def code(prefix: str, idx: int) -> str:
    return f'{DEMO_MARKER}-{prefix}-{idx:02d}'


def log_created(stdout, style, label: str, created: int, skipped: int = 0):
    if created:
        stdout.write(style.SUCCESS(f'  + {label}: {created} kayıt'))
    elif skipped:
        stdout.write(f'  = {label}: zaten dolu ({skipped})')
