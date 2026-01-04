import json
from pathlib import Path

from django import template
from django.conf import settings

register = template.Library()


def _load_manifest():
    manifest_root = Path(settings.BASE_DIR / "static" / "app")
    manifest_paths = [
        manifest_root / "manifest.json",
        manifest_root / ".vite" / "manifest.json",
    ]
    for manifest_path in manifest_paths:
        if manifest_path.exists():
            with manifest_path.open() as manifest_file:
                return json.load(manifest_file)
    return {}


@register.simple_tag
def vite_asset(entry: str, asset_type: str = "script") -> str:
    """
    Resolve a built asset from Vite's manifest.
    Returns an empty string if the manifest has not been generated yet.
    """
    manifest = _load_manifest()
    if not manifest:
        return ""

    asset = manifest.get(entry)
    if not asset:
        raise ValueError(f"Missing entry '{entry}' in Vite manifest.")

    if asset_type == "script":
        return f"{settings.STATIC_URL}app/{asset['file']}"
    if asset_type == "css":
        css_files = asset.get("css", [])
        return f"{settings.STATIC_URL}app/{css_files[0]}" if css_files else ""
    return ""
