from django.contrib import admin

from flat_file_exporter.models import ExportedFile, ExportStakeholder


class ExportStakeholderInline(admin.TabularInline):
    model = ExportStakeholder
    extra = 0


@admin.register(ExportedFile)
class ExportedFileAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "requested_at", "kind", "content_type", "size", "processing_time"]
    list_filter = ["status", "kind", "content_type"]
    search_fields = ["name", "validation_code", "notes"]
    readonly_fields = ["validation_code", "requested_at"]
    inlines = [ExportStakeholderInline]
