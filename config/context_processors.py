from django.conf import settings


def brand(request):
    """Expose project branding (``settings.BRAND``) to every template as ``brand``."""
    return {"brand": settings.BRAND}
