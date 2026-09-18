import markdown
from django import template
from django.forms.widgets import CheckboxInput
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def is_checkbox(field):
    """True if the bound field renders as a checkbox."""
    return isinstance(field.field.widget, CheckboxInput)


@register.filter
def add_class(field, css_class):
    """Add a CSS class to a form field widget."""
    existing = field.field.widget.attrs.get("class", "")
    combined = f"{existing} {css_class}".strip() if existing else css_class
    return field.as_widget(attrs={"class": combined})


@register.filter
def bootstrap_col_class(field_row):
    """Bootstrap ``col-md-N`` class for a row with the given number of fields (12-column grid)."""
    try:
        count = len(field_row)
    except TypeError:
        count = 1
    return f"col-md-{12 // max(count, 1)}"


@register.filter
def format_duration(value):
    """Seconds as a friendly duration (e.g. 38m56s, 1h5m2s)."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return "0s"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return "".join(parts)


@register.filter
def render_markdown(value):
    """Markdown to HTML. The text comes from developer-written docstrings and form help texts, not from end users."""
    return mark_safe(markdown.markdown(value or ""))  # noqa: S308
