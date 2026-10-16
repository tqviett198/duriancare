from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    farm = models.ForeignKey("farms.Farm", null=True, blank=True, on_delete=models.SET_NULL)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=40)
    entity_type = models.CharField(max_length=40)
    entity_id = models.BigIntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


def audit(*, farm, actor, action, entity, **metadata):
    return AuditLog.objects.create(
        farm=farm, actor=actor, action=action,
        entity_type=entity.__class__.__name__, entity_id=entity.pk, metadata=metadata,
    )
