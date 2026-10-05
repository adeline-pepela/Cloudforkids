from .models import SiteSetting


def site_settings(request):
    """`site` = the editable website wording and contact details (Admin > Site settings)."""
    return {"site": SiteSetting.load()}
