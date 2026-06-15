import sys

errors = []

# Test services/proxy imports
try:
    from app.services.proxy import ProxyManager, ProxyPool, ProxyConfig, get_proxy_manager
    print('✅ services/proxy - OK')
except Exception as e:
    errors.append(f'services/proxy: {e}')

# Test services/wechat_mp imports
try:
    from app.services.wechat_mp import WechatMPService, WechatMPAPIClient, WechatMPParser
    print('✅ services/wechat_mp - OK')
except Exception as e:
    errors.append(f'services/wechat_mp: {e}')

# Test services/ebook imports
try:
    from app.services.ebook import EbookService, get_ebook_service
    print('✅ services/ebook - OK')
except Exception as e:
    errors.append(f'services/ebook: {e}')

# Test models
try:
    from app.db.models.wechat_mp import WechatMPDownload, WechatMPDownloadCreate, WechatMPDownloadResponse
    from app.db.models.platform_connection import PlatformType
    assert hasattr(PlatformType, 'WECHAT_MP'), 'WECHAT_MP not in PlatformType'
    print('✅ db/models - OK')
except Exception as e:
    errors.append(f'db/models: {e}')

# Test API routes
try:
    from app.api.v1 import wechat_mp, ebook
    print('✅ api/v1 routes - OK')
except Exception as e:
    errors.append(f'api/v1 routes: {e}')

# Test sniffer/cert
try:
    from app.services.proxy.sniffer import ProxySniffer
    from app.services.proxy.cert import CertManager
    print('✅ proxy sniffer/cert - OK')
except Exception as e:
    errors.append(f'proxy sniffer/cert: {e}')

if errors:
    print(f'\n⚠️  {len(errors)} error(s):')
    for e in errors:
        print(f'  - {e}')
else:
    print('\n🎉 All checks passed!')
