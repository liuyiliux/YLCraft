"""动图提示词构建：多格图（frame sheet）的提示词模板。

**为什么单独成模块**：动图提示词是**中英双语**的——英文是实测验证过的原句
（发给模型以它为准），中文是给人看、给人改的。两版内容对应但措辞不同，
必须由同一个函数按语言产出，否则两版会各自漂移、改了一版另一版不跟着变。

**核心约束：预览与生成必须共用本模块**。一旦两份实现各写各的，预览就会与
实际不一致，用户照着预览调半天、生成出来却不一样——这是
`services/image_annotation` 已有的同类教训（见架构文档「核心约束」一节）。

实测得到的几条硬约束（不要随手删）：

1. **禁止「每行重开一次」**。模型容易把 4×4 理解成"4 行 × 每行一次独立运动"，
   于是每换一行就跳回起点，播放出来是左右来回摆。必须显式写明第 N+cols 格
   接着第 N 格。
2. **四类动效的写法不能互相照抄**。相机环绕要背景横移（否则转不显），
   角色动作要背景锁死（照抄环绕的横移会把平涂底搅花），表情类机位要锁得最死
   （脸对 1% 横移都敏感，全身横移 1% 却看不出来）。
3. **格数少更好**。gpt-image-2 实测 16 格会抖，8 格（2×4）最稳。
4. **prompt 总量控制在 6000 字符内**（实测 6449 可用、9213 被接口拒收）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

#: 触发整份 prompt 超限的阈值。超了接口会拒收，宁可本地报错也不浪费请求。
PROMPT_CHAR_LIMIT = 6000

MotionKind = Literal["orbit", "character", "speed", "expression"]
GridLayout = Literal["4x4", "2x4", "1x4"]
LoopMode = Literal["pingpong", "cycle"]
PromptLang = Literal["zh", "en"]


@dataclass(frozen=True)
class GridSpec:
    """一个排布选项。"""

    key: GridLayout
    label: str
    rows: int
    cols: int
    note: str
    recommended: bool = False

    @property
    def cells(self) -> int:
        return self.rows * self.cols

    @property
    def step_degrees(self) -> float:
        """每格转过的角度。环绕类按 60° 总跨度均分。"""
        return 60.0 / (self.cells - 1) if self.cells > 1 else 60.0


GRID_LAYOUTS: tuple[GridSpec, ...] = (
    GridSpec("4x4", "16 格", 4, 4, "画面最流畅，但实测容易抖动、换行处会「弹回」"),
    GridSpec("2x4", "8 格", 2, 4, "实测最稳：一致性高、转动幅度反而更大", recommended=True),
    GridSpec("1x4", "4 格", 1, 4, "最保险，但动作幅度小、观感偏顿"),
)


@dataclass(frozen=True)
class MotionKindSpec:
    """一类动效。``prefer_reference`` 表示推荐带参考图，**不是必须**。

    文生图同样能做环绕/表情包，只是模型每格都在重新构想同一主体、主体容易
    越走越样；带参考图（图生图）才锁得住外观。因此这里只做提示，不做禁用。
    """

    key: MotionKind
    label: str
    motion: str
    usage: str
    prefer_reference: bool
    stability: Literal["good", "fair", "unknown"]
    default_loop: LoopMode
    #: 每格的"变化量"该用什么单位描述（中文 / 英文模板，含 `{step}` 占位）。
    #:
    #: ⚠️ 四类动效**不能用同一句话**。踩过的坑：连续性那段曾经一律写
    #: "每格约 8.571 度" —— 那是 `60° ÷ 7` 算出来的**相机环绕专用**数值，
    #: 却被角色动作 / 速度型 / 表情包照抄。表情包根本没有"环绕角度"这回事，
    #: 等于告诉模型"每格要转 8.571 度"，与"机位完全锁死"直接矛盾。
    #: 这很可能是那几类实测不稳定的一个原因。
    change_zh: str = "变化量必须完全相同"  # TEMP-REVERT
    change_en: str = "the change between adjacent cells must be identical"


MOTION_KINDS: tuple[MotionKindSpec, ...] = (
    MotionKindSpec(
        "orbit", "相机环绕", "镜头绕着主体转，背景横移",
        "电商主图、详情页、产品展示", True, "fair", "pingpong",
        # 环绕是唯一有"角度"概念的：整段扫过 60°，按格数均分。
        change_zh="每格约 {step} 度（整段扫过 60 度）",
        change_en="about {step} degrees per cell (60 degrees across the sheet)",
    ),
    MotionKindSpec(
        "character", "角色动作", "主体自己打一套招式，背景不动",
        "游戏人物放技能、角色动作", False, "unknown", "cycle",
        # 动作没有角度；用"动作幅度"描述。**不要塞角度** —— 那是环绕的算法。
        change_zh="每格的姿态幅度递进相同（不要忽大忽小，也不要中途停住）",
        change_en="each cell advances the pose by the same amount",
    ),
    MotionKindSpec(
        "speed", "速度型动作", "主体做动作 + 背景向后掠",
        "飞行、奔跑、冲刺", False, "unknown", "cycle",
        change_zh="每格的主体位移与背景后掠量相同（速度要匀速，不要忽快忽慢）",
        change_en="the same amount of subject displacement and background sweep per cell",
    ),
    MotionKindSpec(
        "expression", "表情包", "一张脸的表情连续变化，其余全不动",
        "聊天表情包、情绪演出", True, "good", "cycle",
        # 表情包**机位锁死**，绝不能提"角度/位移" —— 那与"任何东西都不变"矛盾。
        change_zh="每格的**表情强度**递进相同（脸的位置、大小、朝向全程不动）",
        change_en="the same amount of expression change per cell (face position, size and angle stay fixed)",
    ),
)


def grid_spec(layout: GridLayout) -> GridSpec:
    for spec in GRID_LAYOUTS:
        if spec.key == layout:
            return spec
    raise ValueError(f"未知的格子排布：{layout}")


def motion_kind_spec(kind: MotionKind) -> MotionKindSpec:
    for spec in MOTION_KINDS:
        if spec.key == kind:
            return spec
    raise ValueError(f"未知的动效类型：{kind}")


@dataclass(frozen=True)
class PromptBlock:
    """一段系统追加的提示词。

    分块返回是为了让前端标出「哪段是系统加的」——用户必须能看见、能改、能关，
    否则会被一段看不见的固定文案绑定，出问题时无从下手。
    """

    id: str
    title: str
    why: str
    text: str


def build_prompt_blocks(
    *,
    kind: MotionKind,
    layout: GridLayout,
    lang: PromptLang,
    subject: str = "",
) -> list[PromptBlock]:
    """按动效类型与排布产出系统提示词块（中文版）。"""
    grid = grid_spec(layout)
    motion = motion_kind_spec(kind)
    kind_spec = motion
    who = subject.strip() or ("参考图中的主体" if lang == "zh" else "the subject in the reference image")
    step = grid.step_degrees

    return [
        PromptBlock(
            id="task",
            title="任务与格数",
            why="告诉模型这是一张多格图、按什么顺序读，而不是多张独立图",
            text=(
                f"【任务】生成一张 {grid.rows}×{grid.cols} 多格图"
                f"（共 {grid.cells} 格，从左到右、从上到下阅读），表现同一段连续动作。\n\n"
                f"【主体】{who}"
            ),
        ),
        PromptBlock(
            id="motion",
            title="动效写法",
            why=f"「{motion.label}」专属规则——四类动效不能互相照抄",
            text=_motion_rule_zh(kind, grid),
        ),
        PromptBlock(
            id="continuity",
            title="连续性约束（关键）",
            why="防止模型把每一行当成一次独立运动，导致来回摆动",
            text=(
                f"【连续性】这 {grid.cells} 格**不是**多张独立画面，**也不是**按行分组的网格，\n"
                f"而是同一段运动被等时间采样 {grid.cells} 次。\n"
                # ⚠️ 这里按**动效类型**取描述。曾经一律写"每格约 8.571 度"——
                # 那是环绕专用的算法（60°÷7），表情包/动作类照抄会与自身规则打架。
                f"- 相邻两格之间：{kind_spec.change_zh.format(step=f'{step:.4g}')}。\n"
                f"- 动作**不得在每行开头重新开始**：第 {grid.cols + 1} 格直接接着第 {grid.cols} 格，\n"
                f"  就像第 2 格接着第 1 格一样。\n"
                f"- 整张表只有一个起点（第 1 格）和一个终点（第 {grid.cells} 格）。\n"
                f"- 每行开头主体回到相似朝向的图 = 失败。"
            ),
        ),
        PromptBlock(
            id="locked",
            title="固定项",
            why="锁死不该变的东西（光影、背景、道具），避免闪烁与漂移",
            text=(
                f"【不得变化】\n"
                f"- {grid.cells} 格的光照、白平衡、阴影完全一致：不闪烁、不偏色、不忽明忽暗。\n"
                f"- 不得增删任何物体、道具或背景元素。"
            ),
        ),
        PromptBlock(
            id="output",
            title="输出格式",
            why="保证切帧时格子对齐、没有多余元素",
            text=(
                f"【输出】\n"
                f"- {grid.rows} 行 {grid.cols} 列，格子等大，无可见网格线，格间无缝隙。\n"
                f"- 无边框、无文字、无数字、无水印、无标题、无 logo。"
            ),
        ),
    ]


def build_prompt_blocks_en(
    *,
    kind: MotionKind,
    layout: GridLayout,
    subject: str = "",
) -> list[PromptBlock]:
    """英文版：实测验证过的原句，发给模型以这一版为准。"""
    grid = grid_spec(layout)
    motion = motion_kind_spec(kind)
    kind_spec = motion
    who = subject.strip() or "the subject in the reference image"
    step = grid.step_degrees

    return [
        PromptBlock(
            id="task",
            title="Task & grid",
            why="ONE sheet read in order, not N separate images",
            text=(
                f"TASK\nCreate a {grid.rows}x{grid.cols} sprite sheet "
                f"({grid.cells} cells, read left to right, top to bottom)\n"
                f"of ONE continuous motion.\n\nSUBJECT - the pivot\n{who}"
            ),
        ),
        PromptBlock(
            id="motion",
            title="Motion rules",
            why=f'Rules specific to "{motion.label}" - the four kinds must not copy each other',
            text=_motion_rule_en(kind, grid),
        ),
        PromptBlock(
            id="continuity",
            title="Continuity (critical)",
            why="Stops the model treating each row as a separate move, which reads as swinging",
            text=(
                f"THE ARC IS MONOTONIC\n"
                f"- The {grid.cells} cells are NOT separate shots and NOT rows of a grid.\n"
                f"- They are ONE single move, sampled {grid.cells} times.\n"
                # 按动效类型取描述：环绕用角度，动作/速度/表情各用自己的度量。
                f"- The change between ANY two consecutive cells is EXACTLY THE SAME "
                f"({kind_spec.change_en.format(step=f'{step:.4g}')}).\n"
                f"- The motion must not restart at the start of a row. Cell {grid.cols + 1}\n"
                f"  continues directly from cell {grid.cols}, exactly as cell 2 continues from cell 1.\n"
                f"- There is exactly ONE start (cell 1) and ONE end (cell {grid.cells}).\n"
                f"- A sheet in which the subject returns to a similar orientation at the start of a row is a FAILED sheet."
            ),
        ),
        PromptBlock(
            id="locked",
            title="What must not change",
            why="Locks lighting/background/props so nothing flickers or drifts",
            text=(
                f"WHAT MUST NOT CHANGE\n"
                f"- Identical lighting, white balance and shadow in all {grid.cells} cells:\n"
                f"  no flicker, no colour drift, no brightness change.\n"
                f"- Never add or remove an object, a prop or a background element."
            ),
        ),
        PromptBlock(
            id="output",
            title="Output format",
            why="Keeps cells aligned for slicing and free of extra elements",
            text=(
                f"OUTPUT\n"
                f"- {grid.rows} rows, {grid.cols} columns, equal cells, no visible grid lines, no gaps.\n"
                f"- No borders, frames, text, numbers, watermarks, captions or logos."
            ),
        ),
    ]


def compose_final_prompt(
    *,
    user_prompt: str,
    blocks: Sequence[PromptBlock],
    disabled_ids: Sequence[str] = (),
    optimized: bool = False,
) -> str:
    """拼出**真正发给模型**的完整提示词。

    与预览走同一个函数（见模块头「核心约束」）。

    Args:
        user_prompt: 用户填的主提示词。
        blocks: 系统追加的块。
        disabled_ids: 被用户关掉的块 id。
        optimized: AI 优化过的提示词。**为真时不再追加任何系统块**——
            优化结果已按该动效写法写全，再追加会重复甚至冲突（两段措辞
            打架时模型会被带偏）。
    """
    parts = [user_prompt.strip()]
    if not optimized:
        skipped = set(disabled_ids)
        parts.extend(b.text for b in blocks if b.id not in skipped)
    return "\n\n".join(p for p in parts if p)


def exceeds_limit(prompt: str) -> bool:
    """是否超出实测可接受的字符上限。"""
    return len(prompt) > PROMPT_CHAR_LIMIT


def apply_block_overrides(
    blocks: Sequence[PromptBlock],
    overrides: dict[str, str] | None,
) -> list[PromptBlock]:
    """把用户改过的块文本套上去；返回新的块列表（不改原对象）。

    **为什么要有编辑而不是只有开关**：这套规则是**按我的假设写的默认值**，
    而用户的素材与用法千差万别。实测踩到的例子：
    - 「表情包」原本写死"除了表情画面里任何东西都不变"，而用户要的是
      **表情变 + 小动作，但主体不变**；
    - 「连续性」原本四类共用一句"每格约 8.571 度"（相机环绕的算法），
      表情包照抄会自相矛盾。

    结论：**能改比写得准更重要** —— 规则是默认模板，不是圣旨。

    `overrides` 的 key 是块 id，value 是新文本：
    - 空串 → 视为**关掉**这一段（与 `disabled_ids` 等价，调用方二选一即可）
    - 不存在 / None → 用默认文本
    """
    if not overrides:
        return list(blocks)
    out: list[PromptBlock] = []
    for b in blocks:
        custom = overrides.get(b.id)
        if custom is None:
            out.append(b)
        elif custom.strip():
            # frozen dataclass：用 replace 而不是改字段
            out.append(replace(b, text=custom.strip()))
        # 空串表示用户清空了这段 → 不追加（等于关掉）
    return out


def blocks_to_prompt(
    *,
    user_prompt: str,
    blocks: Sequence[PromptBlock],
    disabled_ids: Sequence[str] = (),
    overrides: dict[str, str] | None = None,
    optimized: bool = False,
) -> str:
    """**预览与生成共用的唯一入口**：套用用户改动 → 拼出最终提示词。

    直接把 `apply_block_overrides` + `compose_final_prompt` 串起来，
    避免调用方漏掉其中一步（漏了就会出现"预览能改、生成不改"的漂移）。
    """
    return compose_final_prompt(
        user_prompt=user_prompt,
        blocks=apply_block_overrides(blocks, overrides),
        disabled_ids=disabled_ids,
        optimized=optimized,
    )


def default_loop(kind: MotionKind) -> LoopMode:
    """按动效类型给推荐循环方式。

    环绕类必须 pingpong（格图只覆盖单程角度，正放完镜像回退才无缝）；
    表情/动作类要 cycle（最后一格回到第一格才闭合）。
    """
    return motion_kind_spec(kind).default_loop


def _motion_rule_zh(kind: MotionKind, grid: GridSpec) -> str:
    if kind == "orbit":
        return (
            "【相机环绕】\n"
            "- 镜头绕主体垂直轴转；主体自身不移动、不自转。\n"
            "- 主体始终位于画面正中，镜头始终对准它。\n"
            "- 位移由背景承载：背景在主体身后横向滑过（近处快、远处慢）。\n"
            "- 距离、高度、焦距全程不变：不推拉、不缩放、不升降、不俯仰、不翻滚。\n"
            f"- 全程约扫过 60 度，分成 {grid.cells - 1} 个等步，每步约 {grid.step_degrees:.4g} 度。\n"
            "- 是【镜头】在环绕；主体不转向镜头、不露出背面。"
        )
    if kind == "character":
        return (
            "【机位完全锁死 + 角色动作】\n"
            "- 镜头完全不动：不环绕、不平移、不缩放、不推拉。\n"
            "- 背景锁死，不移动。\n"
            "- 动作全部发生在角色身上：完成一套连续动作。\n"
            "- 角色保持在画面中部，不横穿画面。\n"
            "- 最后一格回到起始姿势，闭合循环。"
        )
    if kind == "speed":
        return (
            "【机位锁死 + 背景后掠】\n"
            "- 镜头完全不动。\n"
            "- 角色不横穿画面：保持在画面中部。\n"
            "- 速度感只来自背景向后飞速掠过。\n"
            "- 近处背景元素移动快，远处慢（视差）。\n"
            "- 角色完成一套连续动作，例如整圈空翻或奔跑循环。"
        )
    return (
        "【机位完全锁死 + 表情为主，允许小幅动作】\n"
        "- **机位锁死**：镜头不环绕、不平移、不缩放、不推拉。\n"
        "- 头部的位置和大小在每一格中保持一致（脸对 1% 横移都极敏感）。\n"
        "- 表情变化是主线：眼睑、嘴巴、瞳孔、眉毛。\n"
        "- **允许附加小幅肢体/尾巴/耳朵等动作**（如摇尾、抬手、点头），\n"
        "  但幅度要小、要连续，**不得改变主体的身份特征与整体轮廓**。\n"
        "- 若不需要任何附加动作，就只做表情 —— 不要凭空添加大幅位移。\n"
        "- 表情不得在极端之间瞬间切换，节拍之间平滑过渡。\n"
        "- 任何不对称特征必须用【观众视角】给方位（如「观众视角左侧的嘴角」），禁止用「他的左边」。\n"
        "- 最后一格回到第一格的中性表情，闭合循环。"
    )


def _motion_rule_en(kind: MotionKind, grid: GridSpec) -> str:
    if kind == "orbit":
        return (
            "CAMERA ORBIT\n"
            "- The camera orbits the SUBJECT's vertical axis; the SUBJECT itself does not move or spin.\n"
            "- The SUBJECT STAYS IN THE MIDDLE OF THE FRAME. The camera keeps aiming at it.\n"
            "- The travelling is done by the BACKGROUND, sliding across the frame behind the SUBJECT\n"
            "  (near features FASTER than far ones).\n"
            "- CONSTANT distance, height and focal length: no dolly, no zoom, no rise, no tilt, no roll.\n"
            f"- The arc covers about 60 degrees in {grid.cells - 1} equal steps "
            f"of about {grid.step_degrees:.4g} degrees.\n"
            "- It is the CAMERA that orbits. The subject never turns to face the camera and never shows its back."
        )
    if kind == "character":
        return (
            "CAMERA FULLY LOCKED + CHARACTER ACTION\n"
            "- The camera does NOT move at all: no orbit, no pan, no zoom, no dolly.\n"
            "- The background is locked and does not move.\n"
            "- The action is entirely in the character: it performs one continuous move.\n"
            "- The character stays centred and does not walk across the frame.\n"
            "- The last cell returns to the starting pose, closing the loop."
        )
    if kind == "speed":
        return (
            "CAMERA LOCKED + BACKGROUND RUSHING PAST\n"
            "- The camera does NOT move at all.\n"
            "- The character does NOT cross the frame: it stays centred.\n"
            "- The speed comes ONLY from the background rushing backwards past the camera.\n"
            "- Near background elements move FAST, far ones move SLOWLY (parallax).\n"
            "- The character performs one continuous action, such as a full tumble or sprint cycle."
        )
    return (
        "CAMERA FULLY LOCKED + EXPRESSION-LED, SMALL MOTION ALLOWED\n"
        "- The CAMERA is fully locked: no orbit, no pan, no zoom, no dolly.\n"
        "- The head stays in exactly the same place and at exactly the same size in every cell\n"
        "  (the face is far more sensitive to sideways drift than a whole body).\n"
        "- Expression is the through-line: eyelids, mouth, pupils and eyebrows.\n"
        "- SMALL secondary motion IS allowed (tail wag, paw lift, nod, ear flick),\n"
        "  but keep it subtle and continuous, and never alter the subject's identity\n"
        "  or its overall silhouette.\n"
        "- If no secondary motion is wanted, change only the expression -\n"
        "  do not invent large displacement.\n"
        "- The face must never snap instantly from one extreme to another; blend between beats.\n"
        '- Any asymmetric feature must be named from the VIEWER\'s side\n'
        '  (e.g. "the corner of the mouth on the viewer\'s left"), never "his left".\n'
        "- The last cell returns to the neutral expression of the first cell, closing the loop."
    )
