"""Which call provider a campaign may use. Sample (demo) campaigns can NEVER reach a real provider."""
from member3.integrations.base import CallProvider
from member3.integrations.demo_provider.provider import DemoProvider
from member3.integrations.factory import build_provider

from ..models import Campaign


def provider_for_campaign(settings, campaign: Campaign, override: CallProvider | None = None) -> CallProvider:
    """Raises ProviderError when the configured real provider is incomplete."""
    if campaign.is_demo:
        return DemoProvider()
    if override:
        return override
    return build_provider(settings)
