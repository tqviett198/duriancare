from django.db import migrations, models

GRADE_MAP = {"A": "GRADE_1", "B": "GRADE_2", "C": "GRADE_3"}


def forwards(apps, schema_editor):
    BatchStock = apps.get_model("harvests", "BatchStock")
    for old, new in GRADE_MAP.items():
        BatchStock.objects.filter(grade=old).update(grade=new)


def backwards(apps, schema_editor):
    BatchStock = apps.get_model("harvests", "BatchStock")
    for old, new in GRADE_MAP.items():
        BatchStock.objects.filter(grade=new).update(grade=old)


class Migration(migrations.Migration):

    dependencies = [
        ("harvests", "0002_remove_harvestbatch_batch_phi_date_respected_and_more"),
    ]

    operations = [
        # Mở rộng max_length trước (6 -> 8) để chứa "GRADE_1"
        migrations.AlterField(
            model_name="batchstock",
            name="grade",
            field=models.CharField(
                choices=[
                    ("GRADE_1", "Loại 1 (xuất khẩu)"),
                    ("GRADE_2", "Loại 2 (nội địa cao cấp)"),
                    ("GRADE_3", "Loại 3 (nội địa thường)"),
                    ("REJECT", "Loại thải"),
                ],
                max_length=8,
            ),
        ),
        # Chuyển dữ liệu cũ A/B/C -> GRADE_1/2/3
        migrations.RunPython(forwards, backwards),
    ]
