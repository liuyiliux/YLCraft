"""回归：素材库「来源」枚举只有一处定义，且前端确实在用它。

**为什么要有这个文件**：这个枚举此前在三个地方各写一份 ——
后端入库写 node metadata 的 `source`、后端出卡把 `source` 映射成对外的
`source_type`、前端硬编码一份下拉选项与中文名。三份靠人记着同步，于是踩了：

动图入库自创 `source="motion_gif"`，前端选项里没有 → 卡片显示"未知来源"，
一点「AI生成」筛选就被排除。用户看到的是"存入素材库成功，再查素材库怎么看不到"。
**后端一切正常、接口 success、数据库里躺着** —— 只在按正常路径去找时消失。

所以这里锁三件事：
1. 枚举只有 `source_taxonomy` 一处定义；
2. 它经 `GET /assets/meta` 暴露给前端；
3. 前端页面里**没有**残留的硬编码副本。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.asset_hub import source_taxonomy


def _frontend_assets_page() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "pages"
        / "assets"
        / "index.tsx"
    )


class TestTaxonomyIsSingleSourceOfTruth:
    def test_every_stored_source_maps_to_a_known_group(self):
        """每个登记的入库值都必须能映射到一个展示分组。

        映射不到 = 用 `source_type_of` 原样返回 = 前端筛选认不出来 ——
        正是动图当初的处境。
        """
        known_groups = {g.value for g in source_taxonomy.SOURCE_GROUPS}
        for stored in source_taxonomy.KNOWN_STORED_SOURCES:
            mapped = source_taxonomy.source_type_of(stored)
            assert mapped in known_groups, (
                f"入库值 {stored!r} 映射到 {mapped!r}，不在任何展示分组里 —— "
                "素材库会把它当成未知来源并排除出所有筛选"
            )

    def test_ai_generated_group_covers_all_ai_pipelines(self):
        """AI 类流程都要归到 `ai_generated`，否则会被「AI生成」筛选漏掉。"""
        for stored in ("image_generation", "character_portrait", "motion_gif"):
            assert source_taxonomy.is_ai_generated(stored), (
                f"{stored!r} 没被算作 AI 生成 —— 一点「AI生成」筛选就会漏掉它"
            )
            assert source_taxonomy.source_type_of(stored) == "ai_generated"

    def test_filter_options_are_unique_and_have_labels(self):
        options = source_taxonomy.filter_options()
        values = [o["value"] for o in options]
        assert len(values) == len(set(values)), f"筛选选项有重复：{values}"
        for option in options:
            assert option["value"], "筛选选项的 value 不能为空"
            assert option["label"], f"筛选选项 {option['value']} 没有中文名"

    def test_unknown_stored_source_is_reported_not_silently_grouped(self):
        """未登记的值**原样返回**，不硬塞进某个已知分组。

        塞进去会更糟：它会让这个陌生值悄悄混进那个分组的筛选结果里，
        掩盖真正的"忘记登记"。
        """
        assert source_taxonomy.source_type_of("something_new") == "something_new"
        assert not source_taxonomy.is_ai_generated("something_new")

    def test_guard_rejects_unregistered_source(self):
        """入库自检必须**抛错** —— 未登记的值不会自己报错，只会让资产消失。"""
        with pytest.raises(ValueError, match="未登记"):
            source_taxonomy.assert_known_source("brand_new_thing", where="pytest")
        # 登记过的值不该抛
        source_taxonomy.assert_known_source("image_generation", where="pytest")

    def test_motion_gif_legacy_value_still_maps_to_ai_generated(self):
        """历史数据兼容：早期动图存的是自创的 `motion_gif`，也要显示成 AI 生成。"""
        assert source_taxonomy.source_type_of("motion_gif") == "ai_generated"
        assert source_taxonomy.source_label("ai_generated") == "AI生成"


class TestBackendExposesTheEnum:
    def test_meta_endpoint_returns_options_and_labels(self):
        """前端靠这个端点拿枚举 —— 它必须存在且字段齐全。"""
        import asyncio

        from app.api.v1.assets import get_assets_meta

        payload = asyncio.run(get_assets_meta())
        assert payload["success"] is True
        assert payload["source_type_options"], "筛选选项为空，前端下拉会是空的"
        assert "ai_generated" in {o["value"] for o in payload["source_type_options"]}
        assert payload["source_type_labels"].get("ai_generated") == "AI生成"
        assert payload["unknown_source_label"]

    def test_meta_endpoint_matches_the_taxonomy(self):
        import asyncio

        from app.api.v1.assets import get_assets_meta

        payload = asyncio.run(get_assets_meta())
        assert payload["source_type_options"] == source_taxonomy.filter_options()
        assert payload["source_type_labels"] == source_taxonomy.label_map()

    def test_route_is_registered(self):
        """忘了挂路由的话前端永远拿兜底值 —— 静默退化成硬编码。"""
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/api/v1/assets/meta" in paths


class TestFrontendDoesNotHardcodeTheEnum:
    """前端**不该**再留一份来源选项副本。

    这不是洁癖：留一份就又多一处要同步的地方，而这次的 bug 正是
    "多了一份没同步"。所以用测试钉住 —— 页面里只能有兜底值，
    不能有完整列表。
    """

    @pytest.mark.skipif(
        not _frontend_assets_page().exists(), reason="前端源码不在本机（多机开发时）"
    )
    def test_no_full_source_option_list_in_page(self):
        source = _frontend_assets_page().read_text(encoding="utf-8")
        # 旧的硬编码常量名必须已经删掉
        assert "SOURCE_TYPE_LABELS" not in source, (
            "页面里还留着 SOURCE_TYPE_LABELS 硬编码 —— 改回从 /assets/meta 拉"
        )
        # 完整选项列表的特征：这些"只有后端才知道"的值不该成片出现在前端
        rare_values = ["novel_bookshelf", "wechat_mp", "legacy_assets", "novel_download"]
        present = [v for v in rare_values if v in source]
        assert len(present) <= 1, (
            f"页面里出现了多个来源枚举值 {present} —— 像是又抄了一份后端列表。"
            "来源选项一律从 GET /assets/meta 拉"
        )

    @pytest.mark.skipif(
        not _frontend_assets_page().exists(), reason="前端源码不在本机（多机开发时）"
    )
    def test_page_fetches_the_enum_from_api(self):
        source = _frontend_assets_page().read_text(encoding="utf-8")
        assert "getAssetsMeta" in source, (
            "页面没有调用 getAssetsMeta —— 来源下拉会退回兜底值，"
            "后端新增来源时前端看不见"
        )


class TestAssetTypeOptionsMatchTheBackend:
    """回归：前端能选的资产类型，后端必须真的认识。

    踩过的坑：前端自己写了一份资产类型列表，里面 `article` / `document`
    这两个值**后端根本不认**（`_list_asset_hub_cards` 对未登记的
    `asset_type` 直接 `return [], 0`）。用户选了只会看到空列表，
    以为是"这类素材没有"，而不知道是**选项本身无效**。

    未登记的 `source` 会让资产**消失**，未登记的 `asset_type` 会让筛选**永远为空**，
    是同一种病（枚举两边各写一份）的两个症状。
    """

    #: 后端查询真正认识的值 = AssetType 全部值 + `novel` 这个虚拟类型
    @staticmethod
    def _known_types() -> set[str]:
        from app.db.models.asset_hub import AssetType

        return {t.value for t in AssetType} | {"novel"}

    def test_every_option_is_accepted_by_the_list_query(self):
        unknown = source_taxonomy.validate_asset_type_table(self._known_types())
        assert not unknown, (
            f"这些资产类型选项后端不认识：{unknown} —— 用户选了会永远得到空列表。"
            " （踩过：前端写过 article / document，后端从未支持）"
        )

    def test_options_cover_the_common_types(self):
        """常用类型不能漏 —— 漏了用户就筛不出那类素材。"""
        values = {o["value"] for o in source_taxonomy.asset_type_options()}
        for required in ("image", "video", "audio", "text", "character", "novel", "3d_model"):
            assert required in values, f"资产类型下拉漏了 {required}"

    def test_options_are_unique_and_labelled(self):
        options = source_taxonomy.asset_type_options()
        values = [o["value"] for o in options]
        assert len(values) == len(set(values)), f"资产类型选项重复：{values}"
        for option in options:
            assert option["label"], f"{option['value']} 没有中文名"

    def test_meta_endpoint_returns_asset_types(self):
        import asyncio

        from app.api.v1.assets import get_assets_meta

        payload = asyncio.run(get_assets_meta())
        assert payload["asset_type_options"], "资产类型选项为空，前端下拉会是空的"
        assert payload["asset_type_labels"].get("image") == "图片"
        assert payload["asset_type_options"] == source_taxonomy.asset_type_options()

    @pytest.mark.skipif(
        not _frontend_assets_page().exists(), reason="前端源码不在本机（多机开发时）"
    )
    def test_frontend_no_longer_hardcodes_asset_types(self):
        source = _frontend_assets_page().read_text(encoding="utf-8")
        assert "ASSET_TYPE_LABELS" not in source, (
            "页面里还留着 ASSET_TYPE_LABELS 硬编码 —— 改回从 /assets/meta 拉"
        )
        # 后端不认的值不该再出现在前端
        for dead in ("article", "document"):
            assert f"'{dead}'" not in source, (
                f"页面里还出现了后端不认的资产类型 {dead!r}，"
                "用户选了会永远得到空列表"
            )
