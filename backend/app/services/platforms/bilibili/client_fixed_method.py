    async def _get_wbi_keys(self) -> tuple[str, str]:
        """
        获取 WBI keys（用于签名）
        从 B站 API 获取 img_key 和 sub_key
        即使未登录（code=-101），data 中可能仍有 wbi_img
        """
        if self._wbi_keys:
            return self._wbi_keys
        
        try:
            # 调用 B站 API 获取 WBI keys
            url = f"{BASE_URL}/x/web-interface/nav"
            response = await self.request("GET", url)
            
            # 即使返回 code=-101（未登录），data 中可能仍有 wbi_img
            if isinstance(response, dict):
                data = response.get("data", {})
                wbi_img = data.get("wbi_img", {})
                
                if wbi_img:
                    # 提取 img_url 和 sub_url
                    img_url = wbi_img.get("img_url", "")
                    sub_url = wbi_img.get("sub_url", "")
                    
                    import logging
                    logger = logging.getLogger("ylcraft.platforms.bilibili")
                    logger.debug(f"WBI img_url: {img_url}")
                    logger.debug(f"WBI sub_url: {sub_url}")
                    
                    # 从 URL 中提取 key
                    import re
                    img_key = re.search(r'/([^/]+)\.png', img_url)
                    sub_key = re.search(r'/([^/]+)\.png', sub_url)
                    
                    logger.debug(f"img_key match: {img_key}")
                    logger.debug(f"sub_key match: {sub_key}")
                    
                    if img_key and sub_key:
                        self._wbi_keys = (img_key.group(1), sub_key.group(1))
                        self._log(f"Got WBI keys")
                        return self._wbi_keys
            
            # 如果获取失败，使用默认值（长度必须 >= 64）
            default_key = "abcdefghijklmnopqrstuvwxyz1234567890ABCD"
            self._log("Failed to get WBI keys, using default", "warning")
            return (default_key, default_key)
            
        except Exception as e:
            self._log(f"Error getting WBI keys: {e}", "error")
            return ("default_img_key", "default_sub_key")
