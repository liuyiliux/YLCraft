def register_social_connector(
    platform_id: str,
    supported_content_types: list = None,
    supported_media_formats: list = None,
    auth_types: list[str] = None,
    description: str = "",
    **kwargs,  # 接受任意额外参数
):
    """注册社交媒体连接器装饰器"""
    def decorator(cls):
        # 将额外参数设置为类属性（转换为大写）
        for key, value in kwargs.items():
            attr_name = key.upper()
            setattr(cls, attr_name, value)
        
        # 提取已知的 OAuth 参数
        oauth_auth_url = kwargs.get('oauth_auth_url', '')
        oauth_token_url = kwargs.get('oauth_token_url', '')
        oauth_scope = kwargs.get('oauth_scope', '')
        oauth_redirect_uri = kwargs.get('oauth_redirect_uri', '')
        
        SocialConnectorFactory.register(
            platform_id=platform_id,
            connector_class=cls,
            factory_class=getattr(cls, "Factory", None),
            supported_content_types=supported_content_types,
            supported_media_formats=supported_media_formats,
            auth_types=auth_types,
            description=description,
            oauth_auth_url=oauth_auth_url,
            oauth_token_url=oauth_token_url,
            oauth_scope=oauth_scope,
            oauth_redirect_uri=oauth_redirect_uri,
        )
        return cls
    return decorator
