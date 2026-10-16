import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

STATUS_MAP = {"ACTIVE": "CONFIRMED", "VOIDED": "CANCELLED"}


def forwards(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    for old, new in STATUS_MAP.items():
        Sale.objects.filter(status=old).update(status=new)


def backwards(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    for old, new in STATUS_MAP.items():
        Sale.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0001_initial"),
        ("sales", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- Buyer ---
        migrations.CreateModel(
            name="Buyer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, max_length=20)),
                ("address", models.TextField(blank=True)),
                ("tax_code", models.CharField(blank=True, help_text="Mã số thuế (nếu có)", max_length=30)),
                ("is_export", models.BooleanField(default=False, help_text="Khách hàng xuất khẩu")),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="buyers", to="farms.farm")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="buyer",
            constraint=models.UniqueConstraint(fields=("farm", "name"), name="uniq_buyer_name_per_farm"),
        ),

        # --- Sale: grand_total -> total_amount (RENAME để giữ dữ liệu) ---
        migrations.RemoveConstraint(model_name="sale", name="sale_grand_total_nonneg"),
        migrations.RemoveConstraint(model_name="sale", name="sale_paid_lte_total"),
        migrations.RenameField(model_name="sale", old_name="grand_total", new_name="total_amount"),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.CheckConstraint(condition=models.Q(("total_amount__gte", 0)), name="sale_total_amount_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.CheckConstraint(
                condition=models.Q(("paid_amount__lte", models.F("total_amount"))),
                name="sale_paid_lte_total",
            ),
        ),

        # --- Sale: trường mới ---
        migrations.AddField(
            model_name="sale",
            name="buyer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales", to="sales.buyer"),
        ),
        migrations.AddField(
            model_name="sale",
            name="season",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales", to="farms.season"),
        ),
        migrations.AddField(
            model_name="sale",
            name="destination",
            field=models.CharField(default="DOMESTIC", help_text="DOMESTIC hoặc EXPORT", max_length=10),
        ),

        # --- Sale.status: ACTIVE/VOIDED -> CONFIRMED/CANCELLED ---
        migrations.AlterField(
            model_name="sale",
            name="status",
            field=models.CharField(
                choices=[("CONFIRMED", "Đã xác nhận"), ("CANCELLED", "Đã hủy")],
                default="CONFIRMED",
                max_length=10,
            ),
        ),
        migrations.RunPython(forwards, backwards),

        # --- Payment: hỗ trợ hủy thanh toán ---
        migrations.AddField(
            model_name="payment",
            name="status",
            field=models.CharField(choices=[("ACTIVE", "Hiệu lực"), ("VOIDED", "Đã hủy")], default="ACTIVE", max_length=8),
        ),
        migrations.AddField(
            model_name="payment",
            name="void_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="payment",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="voided_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
    ]
