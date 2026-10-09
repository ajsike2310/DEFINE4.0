from .base import CallProvider, ProviderError
from .demo_provider.provider import DemoProvider
from .exotel.provider import ExotelProvider


def build_provider(settings, name: str | None = None) -> CallProvider:
    name = name or settings.call_provider
    if name == "demo":
        return DemoProvider()
    if name == "exotel":
        cb = None
        if settings.public_base_url and settings.exotel_webhook_token:
            cb = f"{settings.public_base_url.rstrip('/')}/api/webhooks/exotel?token={settings.exotel_webhook_token}"
        return ExotelProvider(account_sid=settings.exotel_account_sid, api_key=settings.exotel_api_key,
                              api_token=settings.exotel_api_token, caller_id=settings.exotel_caller_id,
                              flow_url=settings.exotel_flow_url, base_url=settings.exotel_base_url,
                              status_callback=cb, clarify_flow_url=settings.exotel_clarify_flow_url,
                              stream_url=getattr(settings, "exotel_stream_url", ""),
                              allowed_numbers=[n.strip() for n in settings.exotel_allowed_numbers.split(",") if n.strip()])
    raise ProviderError(f"unknown provider {name}")
