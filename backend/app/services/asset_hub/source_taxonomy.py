"""素材库「来源」枚举的**单一真相源**。

**为什么要有这个文件**：这个枚举此前在三个地方各写一份 ——
后端入库时写 node metadata 的 `source`、后端出卡时把 `source` 映射成对外的
`source_type`、前端再硬编码一份下拉选项与中文名。三份靠人记着同步，于是踩了：

- 动图入库自创了 `source="motion_gif"`，前端选项里没有 → 卡片显示"未知来源"，
  一点「AI生成」筛选就被排除。用户看到的是"存进素材库成功，但找不到"。
  后端一切正常、接口 success、数据库里躺着 —— **只在按正常路径去找时消失**。

所以这里把三件事绑在一起定义：**入库写什么值、对外暴露成什么值、给人看叫什么名**。
前端不再硬编码，改为经 `GET /api/v1/assets/meta` 拉取。

## 两个概念不要混

- **入库值**（`source`）：写进 node metadata，表示"这条资产由哪条流程产生"。
  一个入库值可以来自多个流程（`image_generation` 同时被文生图、图生图、动图用）。
- **展示值**（`source_type`）：对外暴露、前端筛选用的分组。多个入库值可归到同一组。

动图**不是**独立的展示分组 —— 它是"AI 生成"下的一个子类，靠 tags(`motion-gif`)
与 `slice_config` 区分。**给子类另立一个 source 值，就等于让它从筛选里消失。**
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetSourceGroup:
    """一个**展示分组**（前端筛选的一项）。"""

    #: 对外暴露的 `source_type` 值，也是前端筛选发给后端的值。
    value: str
    #: 中文名（前端下拉与卡片显示）。
    label: str
    #: 归入本组的**入库值**（node metadata 的 `source`）。
    stored_sources: tuple[str, ...]
    #: 是否出现在前端筛选下拉里。False = 只用于显示，不给用户筛
    #: （例如"未知"，能筛没有意义）。
    filterable: bool = True


#: 展示分组，**顺序即前端下拉顺序**。
SOURCE_GROUPS: tuple[AssetSourceGroup, ...] = (
    AssetSourceGroup("ai_generated", "AI生成", ("image_generation", "character_portrait")),
    AssetSourceGroup("parse", "视频解析", ("download_parse", "parse")),
    AssetSourceGroup("download", "下载", ("download",)),
    AssetSourceGroup("torrent", "磁力/种子", ("torrent",)),
    AssetSourceGroup("novel_download", "小说下载", ("novel_download", "novel_bookshelf")),
    AssetSourceGroup("wechat_mp", "公众号文章", ("wechat_mp",)),
    AssetSourceGroup("upload", "本地上传", ("upload",)),
    AssetSourceGroup("import", "导入", ("import", "imported_file", "legacy_assets")),
    AssetSourceGroup("asset_hub", "资产中枢", ("asset_hub", "crawler"), filterable=False),
    # 兼容：早期动图入库用的是 `motion_gif`（自创值，已修正）。
    # 保留映射，免得**改之前**存下的那批资产在界面上显示成未知。
    AssetSourceGroup(
        "ai_generated",
        "AI生成",
        ("motion_gif",),
        filterable=False,
    ),
)

#: 未命中任何分组时的兜底展示名。
UNKNOWN_SOURCE_LABEL = "未知"

#: 入库值 → 展示分组值。后定义的同名分组会覆盖前者（上面那条兼容项即可生效）。
_STORED_TO_GROUP: dict[str, str] = {}
for _group in SOURCE_GROUPS:
    for _stored in _group.stored_sources:
        _STORED_TO_GROUP[_stored] = _group.value
del _group, _stored


def source_type_of(stored_source: str | None, *, fallback: str = "asset_hub") -> str:
    """把入库值映射成对外的展示值。

    未登记的入库值**原样返回**（而不是硬塞进 "ai_generated"）——
    宁可让它在界面上显示成一个陌生的原始值（提示"这里还没登记"），
    也不要假装它属于某个已知分组：后者会让它悄悄混进那个筛选结果里，
    掩盖真正的登记遗漏。
    """
    if not stored_source:
        return fallback
    return _STORED_TO_GROUP.get(stored_source, stored_source)


def source_label(source_type: str | None) -> str:
    """展示值 → 中文名。"""
    if not source_type:
        return UNKNOWN_SOURCE_LABEL
    for group in SOURCE_GROUPS:
        if group.value == source_type:
            return group.label
    return source_type


def is_ai_generated(stored_source: str | None, source_type: str | None = None) -> bool:
    """这条资产算不算"AI 生成"。

    两个口径都认：入库值（`image_generation`）与展示值（`ai_generated`）——
    调用方手里可能只有其中一个。
    """
    if (source_type or "").lower() == "ai_generated":
        return True
    return source_type_of(stored_source, fallback="") == "ai_generated"


def filter_options() -> list[dict[str, str]]:
    """给前端的筛选下拉：**有序、去重**。"""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for group in SOURCE_GROUPS:
        if not group.filterable or group.value in seen:
            continue
        seen.add(group.value)
        out.append({"value": group.value, "label": group.label})
    return out


def label_map() -> dict[str, str]:
    """给前端的 展示值 → 中文名 映射（含非筛选项，如"未知"）。"""
    out: dict[str, str] = {}
    for group in SOURCE_GROUPS:
        out.setdefault(group.value, group.label)
    out[""] = UNKNOWN_SOURCE_LABEL
    return out


#: 所有**合法**的入库值。入库侧应从这里取值，不要自己拼字符串。
KNOWN_STORED_SOURCES: frozenset[str] = frozenset(_STORED_TO_GROUP)


def assert_known_source(stored_source: str, *, where: str) -> None:
    """入库时自检：值必须是登记过的。

    故意做成**抛错**而不是警告 —— 一个未登记的值不会报任何错，只会让资产
    从素材库筛选里消失。等用户发现"存了但看不到"时，源头已经很难查了。
    """
    if stored_source not in KNOWN_STORED_SOURCES:
        raise ValueError(
            f"{where} 用了未登记的 source={stored_source!r}，"
            f"素材库认不出来（会显示成未知，且被所有来源筛选排除）。"
            f"已登记的值：{sorted(KNOWN_STORED_SOURCES)}。"
            f"需要新增请先加到 app/services/asset_hub/source_taxonomy.py"
        )


# ---------------------------------------------------------------------------
# 资产类型（asset_type）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssetTypeOption:
    """一个**可筛选的**资产类型。

    `value` 是前端发给 `GET /assets?asset_type=` 的值；它**不一定等于**
    数据库里的 `AssetType` 枚举值 —— 有两处刻意的例外：

    - `novel` 是**虚拟类型**：后端按 metadata（`book_url` / `chapters`）
      在 TEXT 里挑出"真小说"，不是一种存储类型；
    - `image` 在查询时会**合并** IMAGE 与 CHARACTER（角色立绘的主表示也是图片，
      图片选择器里必须能选到它）。
    """

    value: str
    label: str


#: 可筛选的资产类型，**顺序即前端下拉顺序**。
#:
#: ⚠️ 这份清单必须与 `_list_asset_hub_cards` 真正认识的值一致：不认识的
#: `asset_type` 会被直接判成空结果（`return [], 0`），用户看到"这个类型下没有素材"
#: 却不知道是选项本身无效。踩过：前端自己写了 `article` / `document` 两个选项，
#: 后端根本不认，选了永远是 0 条。
ASSET_TYPE_OPTIONS: tuple[AssetTypeOption, ...] = (
    AssetTypeOption("video", "视频"),
    AssetTypeOption("image", "图片"),
    AssetTypeOption("audio", "音频"),
    AssetTypeOption("text", "文本"),
    AssetTypeOption("novel", "小说"),
    AssetTypeOption("model", "模型"),
    AssetTypeOption("character", "角色"),
    AssetTypeOption("world_setting", "世界观"),
    AssetTypeOption("workflow", "工作流"),
    AssetTypeOption("3d_model", "3D模型"),
    AssetTypeOption("animation", "动画"),
    AssetTypeOption("subtitle", "字幕"),
    AssetTypeOption("collection", "集合"),
    AssetTypeOption("jianying_draft", "剪映草稿"),
)


def asset_type_options() -> list[dict[str, str]]:
    return [{"value": o.value, "label": o.label} for o in ASSET_TYPE_OPTIONS]


def asset_type_labels() -> dict[str, str]:
    return {o.value: o.label for o in ASSET_TYPE_OPTIONS}


def validate_asset_type_table(known: set[str]) -> list[str]:
    """自检：登记的可筛类型必须都能被 `known` 认识。

    `known` 传后端真正接受的值集合（`AssetType` 的全部值 + `novel` 这个虚拟类型）。
    返回**不认识的那些**，供测试断言为空。

    为什么要在**运行时**也提供这个：这份表与查询逻辑分处两个文件，
    只能靠人对齐。有了它就至少能写测试钉住，而不是等用户选了空选项。
    """
    return sorted(o.value for o in ASSET_TYPE_OPTIONS if o.value not in known)
