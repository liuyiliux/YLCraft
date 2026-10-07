"""图生图「画面批注」：把"你想改成什么样"变成坐标 + 文字的结构化反馈。

**为什么需要**：图生图迭代最难受的地方是**只能用文字描述画面**。你看到"这只手多一根
手指""这个角色不是刚才那套衣服""气泡压在脸上"，但能做的只是把愿望重新打一遍字。而文字
天然丢信息：位置、范围、具体是哪儿。来回三五轮，模型也不知道你到底要什么。

本模块把这一步补上：用户在图上圈一块、写一句话，服务层把这些批注**翻译成给图像模型的
补充提示词**，随主提示词一起提交。批注本身只描述「哪里」和「改什么」，**不替用户写提示词**
——具体怎么措辞由图像模型自己决定。

**借鉴 EditHere（MIT）的设计**：
- 坐标用**相对比例**（0~1）而不是像素：本项目的贴字、地图布局都是相对坐标，与分辨率
  解耦；图像模型只关心"在画面哪个位置"，不关心原图是 1024 还是 3840。
- schema **带版本号**：批注是要持久化和回放的，字段一改就必须能被识别出来，不能悄悄漂移。
- 圈选与文字**解耦**：位置（rectangle）和意见（comment）分两个字段，允许"框了但还没写
  话"，也允许"先写了话再补框"。

**不做什么**：不调用模型，不改代码，不上传图片。本模块纯本地计算。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ylcraft.image_annotation")

#: 当前 schema 版本。批注会被持久化并回放给用户查看，因此字段一旦发布就不能悄悄改语义；
#: 需要变更时升版本号，旧版本继续能读。
SCHEMA_VERSION = "ylcraft.annotation/1.0"

#: 单次提交的批注条数上限。与 EditHere 的 1000 同量级，但这里只防误操作（比如前端把整页
#: 像素点全传上来），不打算支持真的画一千条。
MAX_ANNOTATIONS = 64

#: 单条批注意见的长度上限，防止把整段提示词塞进一个框里。
MAX_COMMENT_LEN = 1000

#: 单次批注注入补充提示词的总长度上限。超过就该让用户精简了——把所有批注硬塞进 prompt
#: 只会挤占主提示词的位置，并且很可能超出图像模型的上下文预算。
MAX_INSTRUCTIONS_LEN = 4000

#: 带框标注图的默认说明。**可被用户改写或置空**——不同模型对这句话的反应差别很大，
#: 用户需要能看见、能调整，而不是被一段看不见的固定文案绑定。
MARKED_IMAGE_HINT = (
    "参考图中有一张是**同一张原图、但用青色方框和编号标出了要改的位置**，"
    "框里的数字对应下面意见的编号。那张图仅用于定位，**不要把框线和编号画进结果**。"
)


class AnnotationError(ValueError):
    """批注不合法。调用方应转成 400，而不是 500。"""


def _num(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationError(f"{field} 必须是数字")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise AnnotationError(f"{field} 不是有效数字")
    return result


def _clip01(value: float, field: str) -> float:
    """把坐标夹到 [0, 1]。

    为什么不直接报错：前端画框时可能出现 1.0000001 这类浮点误差，或者用户把框拖到
    图片边缘外一点点。这两种都不是"错数据"，夹一下比拒绝整次提交更符合直觉——但**夹完
    之后如果 x2<=x1（框退化成一条线或反了），那是真错，必须报错**。
    """
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _normalize_rect(rect: Any, index: int) -> dict[str, float]:
    if not isinstance(rect, dict):
        raise AnnotationError(f"第 {index + 1} 条批注缺少 rectangle")
    raw_x1 = _num(rect.get("x1"), f"annotations[{index}].rectangle.x1")
    raw_y1 = _num(rect.get("y1"), f"annotations[{index}].rectangle.y1")
    raw_x2 = _num(rect.get("x2"), f"annotations[{index}].rectangle.x2")
    raw_y2 = _num(rect.get("y2"), f"annotations[{index}].rectangle.y2")

    x1, x2 = sorted((_clip01(raw_x1, "x1"), _clip01(raw_x2, "x2")))
    y1, y2 = sorted((_clip01(raw_y1, "y1"), _clip01(raw_y2, "y2")))

    if x2 <= x1 or y2 <= y1:
        raise AnnotationError(
            f"第 {index + 1} 条批注的范围为空（拖框时可能没按住边缘）"
        )
    return {"x1": round(x1, 6), "y1": round(y1, 6), "x2": round(x2, 6), "y2": round(y2, 6)}


def normalize_annotations(payload: Any) -> list[dict[str, Any]]:
    """校验并归一化一批批注。

    返回空列表表示"没有批注"，调用方据此**保持原提示词不变**——这是最重要的一条：不批注
    时行为必须与现在完全一致，不能凭空往 prompt 里塞东西。

    坐标一律输出 0~1 相对值，`x2/y2` 为**开区间**（右/下边界不含），与贴字 `items` 的
    `box` 约定一致，两边可以直接换算。
    """
    if payload is None:
        return []
    if isinstance(payload, dict):
        payload = payload.get("annotations")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise AnnotationError("annotations 必须是列表")

    if len(payload) > MAX_ANNOTATIONS:
        raise AnnotationError(f"批注最多 {MAX_ANNOTATIONS} 条，当前 {len(payload)} 条")

    result: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise AnnotationError(f"第 {index + 1} 条批注格式不对")

        comment = str(item.get("comment") or "").strip()
        if not comment:
            # 只有框没有话，等于没提要求。不报错，安静跳过——用户很可能正想再补一句。
            continue
        if len(comment) > MAX_COMMENT_LEN:
            raise AnnotationError(
                f"第 {index + 1} 条批注的意见超过 {MAX_COMMENT_LEN} 字"
            )

        rectangle = _normalize_rect(item.get("rectangle"), index)
        result.append(
            {
                "id": str(item.get("id") or f"a{index + 1}"),
                "comment": comment,
                "rectangle": rectangle,
                "created_at": str(item.get("created_at") or ""),
            }
        )

    if not result:
        return []

    # 去重：同一句话在同一位置反复圈（用户误操作双击）不该让 prompt 里出现两条一样的。
    seen: set[tuple[str, tuple[float, ...]]] = set()
    deduped: list[dict[str, Any]] = []
    for item in result:
        rect = item["rectangle"]
        key = (item["comment"], rect["x1"], rect["y1"], rect["x2"], rect["y2"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # 编号在**过滤与去重之后**统一分配：它必须同时是「提示词里的序号」和
    # 「图上角标的数字」。前端画框时按同一个 number 画角标，两边才对得上。
    for number, item in enumerate(deduped, start=1):
        item["number"] = number
    return deduped


def _describe_position(rect: dict[str, float]) -> str:
    """把框换算成一句人话，附上百分比。

    为什么同时给方向词和百分比：图像模型对"画面左上角三分之一"这种**构图语义**比对
    "x=0.12,y=0.30"这种数字敏感得多；百分比则是精确锚点，防止模型把"上三分之一"理解成
    比实际大得多的区域。两者一起给，模型基本不会找错地方。
    """
    x1, y1, x2, y2 = rect["x1"], rect["y1"], rect["x2"], rect["y2"]
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    col = "左" if cx < 1 / 3 else ("右" if cx > 2 / 3 else "中间")
    row = "上" if cy < 1 / 3 else ("下" if cy > 2 / 3 else "中")

    corner = f"{row}{col}区域" if row != "中" or col != "中间" else "画面中央"
    return f"{corner}（约 x {cx:.0%} / y {cy:.0%} 处）"


def compose_annotation_prompt(
    annotations: list[dict[str, Any]],
    *,
    base_prompt: str = "",
) -> str:
    """把批注翻译成一段追加提示词。

    `base_prompt` 只用于**去重**：如果用户的意见已经原样写进主提示词了，就不在这里重复
    一次（否则图像模型会收到两份同样的强调）。传空串则跳过这项检查。

    **编号与图上角标必须一致**：这里用 `item["number"]`（由 `normalize_annotations` 在
    过滤掉空意见**之后**统一分配）。不要用 `enumerate`——空意见会被滤掉，用 enumerate
    会让「第 2 条意见」和图上的「第 2 个框」错位一格，模型就会把意见安到错误的框上。

    返回空串表示没有可注入的内容，调用方应保持原提示词。
    """
    if not annotations:
        return ""

    base_text = (base_prompt or "").strip()
    lines: list[str] = []
    used = 0

    for item in annotations:
        comment = item["comment"]
        if base_text and comment and comment in base_text:
            # 主提示词里已经写过这句了，跳过以免重复强调挤占预算。
            # 但**不跳编号**：否则模型看到的编号会和图上的角标对不上。
            continue
        number = item.get("number") or 0
        position = _describe_position(item["rectangle"])
        line = f"{number}. {position}：{comment}"
        if used + len(line) > MAX_INSTRUCTIONS_LEN:
            logger.info(
                "annotation prompt truncated at %d annotations (%d chars)",
                index - 1,
                used,
            )
            break
        lines.append(line)
        used += len(line)

    if not lines:
        return ""

    header = (
        "以下是对本张参考图的修改要求，按指定位置严格执行；"
        "画面中未提及的部分保持不变："
    )
    body = "\n".join(lines)
    composed = f"{header}\n{body}"

    # 头部本身也要算进预算，否则一批超长意见会把总长顶破上限。
    if len(composed) > MAX_INSTRUCTIONS_LEN:
        composed = composed[:MAX_INSTRUCTIONS_LEN].rstrip()
    return composed


def build_effective_prompt(
    *,
    base_prompt: str,
    annotations: list[dict[str, Any]],
    marked_reference: bool = False,
    marked_hint: str | None = None,
) -> dict[str, Any]:
    """把主提示词 + 批注 + 标注图说明拼成**最终发给模型的完整提示词**。

    ## 为什么要单独抽出来

    用户需要**看见真正发出去的那串字**——包括系统默认追加的部分。预览接口和真正生成的
    路径必须调同一个函数：一旦两份实现各写各的，预览就会与实际不一致，用户照着预览调
    半天，结果生成出来不一样。**这是本函数存在的唯一理由。**

    ## `marked_hint` 的语义

    `None`（默认）= 用内置默认文案；空字符串 = **不加这句**（用户主动关掉）；
    非空 = 用用户自定义的说明。三种状态必须能区分，所以不能用 `or` 兜底。

    返回结构同时带上分块，便于前端「逐段展示 / 分段编辑」。
    """
    base = (base_prompt or "").strip()
    blocks: list[dict[str, Any]] = []

    hint_text = MARKED_IMAGE_HINT if marked_hint is None else marked_hint.strip()
    if annotations and marked_reference and hint_text:
        blocks.append({"key": "marked_hint", "label": "标注图说明", "content": hint_text})

    if base:
        blocks.append({"key": "base", "label": "主提示词", "content": base})

    annotation_prompt = compose_annotation_prompt(annotations, base_prompt=base)
    if annotation_prompt:
        blocks.append({"key": "annotations", "label": "批注意见", "content": annotation_prompt})

    # 用空行分隔：多数图像后端按段落理解指令，分隔比一坨连写更容易读。
    effective = "\n\n".join(block["content"] for block in blocks if block["content"])
    return {
        "prompt": effective,
        "blocks": blocks,
        # 预览面板要告诉用户「哪些是系统加的」——否则他会把默认文案当成自己写的。
        "system_added": [
            block["key"] for block in blocks if block["key"] in {"marked_hint", "annotations"}
        ],
    }


def annotation_payload_summary(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """给事件日志/血缘用的轻量摘要。

    只留条数与位置，**不带 comment 原文**：批注里常有人写的私人备注或角色设定片段，
    而事件日志和资产元数据会被多处读取和导出，不应该成为绕路带走原文的通道。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "count": len(annotations),
        "rects": [item["rectangle"] for item in annotations],
    }