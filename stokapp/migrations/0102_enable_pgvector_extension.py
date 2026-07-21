# Enable pgvector before any VectorField migrations (e.g. 0103_tekoramemoryembedding).
#
# VectorExtension uses Django's CreateExtension, which is a no-op on non-PostgreSQL
# databases (safe for local SQLite). On PostgreSQL it runs:
#   CREATE EXTENSION IF NOT EXISTS vector
# (idempotent).

from pgvector.django import VectorExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stokapp", "0102_tekora_alert"),
    ]

    operations = [
        VectorExtension(),
    ]
