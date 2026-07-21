"""TEKORA semantic memory embeddings builder (eski chat log'lar için)."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from stokapp.models import TekoraChatLog, TekoraMemoryEmbedding

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "embedding'i olmayan eski TekoraChatLog kayıtları için TekoraMemoryEmbedding üretir."

    def handle(self, *args, **options):
        processed = 0
        skipped = 0
        errors = 0

        qs = TekoraChatLog.objects.annotate(
            has_embedding=Exists(
                TekoraMemoryEmbedding.objects.filter(chat_log_id=OuterRef("pk"))
            )
        ).filter(has_embedding=False)

        for chat_log in qs.iterator():
            try:
                user_msg = chat_log.user_message or ""
                ai_resp = chat_log.ai_response or ""
                combined = (user_msg + "\n" + ai_resp).strip()
                if not combined:
                    skipped += 1
                    continue

                from stokapp.tekora_embeddings import create_memory_embedding_for_chat

                create_memory_embedding_for_chat(chat_log)
                processed += 1
            except Exception:
                errors += 1
                logger.exception("tekora_build_embeddings failed for chat_log_id=%s", chat_log.pk)

        self.stdout.write("[TEKORA EMBEDDINGS]")
        self.stdout.write(f"Processed chat logs: {processed}")
        self.stdout.write(f"Skipped: {skipped}")
        self.stdout.write(f"Errors: {errors}")

