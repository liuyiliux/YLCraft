"""
YLCraft — Story Generator Service
故事生成服务：调用 LLM 生成完整的短剧/漫剧故事结构
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("ylcraft.story.generator")


class StoryGenerationRequest:
    """故事生成请求"""

    def __init__(
        self,
        topic: str,
        style: str = "short_drama",
        num_scenes: int = 8,
    ):
        self.topic = topic
        self.style = style
        self.num_scenes = num_scenes


class CharacterInfo:
    """角色信息（LLM 输出）"""

    def __init__(
        self,
        name: str,
        role: str = "supporting",
        description: str = "",
        personality: str = "",
        appearance: str = "",
        costume_hint: str = "",
        voice_style: str = "",
    ):
        self.name = name
        self.role = role
        self.description = description
        self.personality = personality
        self.appearance = appearance
        self.costume_hint = costume_hint
        self.voice_style = voice_style

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "personality": self.personality,
            "appearance": self.appearance,
            "costume_hint": self.costume_hint,
            "voice_style": self.voice_style,
        }


class SceneInfo:
    """分镜信息（LLM 输出）"""

    def __init__(
        self,
        scene_no: int,
        scene_title: str = "",
        description: str = "",
        dialogue: str = "",
        camera_hint: str = "",
        character_tags: list[str] | None = None,
        emotion: str = "",
    ):
        self.scene_no = scene_no
        self.scene_title = scene_title
        self.description = description
        self.dialogue = dialogue
        self.camera_hint = camera_hint
        self.character_tags = character_tags or []
        self.emotion = emotion

    def to_dict(self) -> dict:
        return {
            "scene_no": self.scene_no,
            "scene_title": self.scene_title,
            "description": self.description,
            "dialogue": self.dialogue,
            "camera_hint": self.camera_hint,
            "character_tags": self.character_tags,
            "emotion": self.emotion,
        }


class StoryGenerationResult:
    """故事生成结果"""

    def __init__(
        self,
        title: str = "",
        plot_outline: str = "",
        style_hint: str = "",
        characters: list[CharacterInfo] | None = None,
        scenes: list[SceneInfo] | None = None,
        music_hint: str = "",
    ):
        self.title = title
        self.plot_outline = plot_outline
        self.style_hint = style_hint
        self.characters = characters or []
        self.scenes = scenes or []
        self.music_hint = music_hint

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "plot_outline": self.plot_outline,
            "style_hint": self.style_hint,
            "characters": [c.to_dict() for c in self.characters],
            "scenes": [s.to_dict() for s in self.scenes],
            "music_hint": self.music_hint,
        }


class StoryGenerationService:
    """故事生成服务"""

    def __init__(self):
        from app.services.backend_registry import BackendManager
        self.backend_manager = BackendManager()

    def _build_prompt(self, request: StoryGenerationRequest) -> str:
        """构建 LLM Prompt"""
        style_name = "都市短剧" if request.style == "short_drama" else "二次元漫剧"

        prompt = f"""你是一个专业的{style_name}剧本作家。
根据用户输入的主题，生成一个完整的{style_name}故事结构。

主题：{request.topic}
风格：{style_name}
集数：1集，约{request.num_scenes}个分镜

请严格按以下JSON格式返回（只需JSON，不要其他文字）：
{{
  "title": "故事标题",
  "plot_outline": "200字故事大纲",
  "style_hint": "视觉风格描述，用于AI生图，包含画面风格、色调、氛围",
  "characters": [
    {{
      "name": "角色名",
      "role": "protagonist|antagonist|supporting|extra",
      "description": "角色定位简述",
      "personality": "性格特点",
      "appearance": "外貌描述（用于AI生图，包含发型、面容、身材等细节）",
      "costume_hint": "服装提示（用于AI生图）",
      "voice_style": "声音/音色建议"
    }}
  ],
  "scenes": [
    {{
      "scene_no": 1,
      "scene_title": "分镜标题",
      "description": "场景描述（用于AI生图）",
      "dialogue": "核心对白/旁白",
      "camera_hint": "镜头语言（特写/全景/中景等）",
      "character_tags": ["角色1", "角色2"],
      "emotion": "情绪基调（紧张/欢乐/悲伤等）"
    }}
  ],
  "music_hint": "配乐建议（风格、情绪、BGM类型）"
}}

要求：
1. 角色 appearance 和 costume_hint 要详细，便于 AI 生图时保持一致性
2. 每个分镜的 description 要包含场景、角色、动作，便于生成配图
3. 角色数量建议 2-5 个，包含主角、反派、配角
4. 分镜数量严格为 {request.num_scenes} 个
"""
        return prompt

    async def generate(self, request: StoryGenerationRequest) -> StoryGenerationResult:
        """
        生成故事结构
        """
        try:
            prompt = self._build_prompt(request)
            logger.info(f"Generating story for topic: {request.topic}")

            # 调用 LLM
            response = await self.backend_manager.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的短剧剧本作家，擅长创作结构清晰、角色鲜明的故事。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,
                max_tokens=4000,
            )

            # 解析 JSON 响应
            content = response.get("content", "")
            if not content:
                raise ValueError("LLM 返回内容为空")

            # 提取 JSON（可能包含 markdown 代码块）
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)

            # 构建结果
            result = StoryGenerationResult(
                title=data.get("title", ""),
                plot_outline=data.get("plot_outline", ""),
                style_hint=data.get("style_hint", ""),
                music_hint=data.get("music_hint", ""),
            )

            # 解析角色
            for char_data in data.get("characters", []):
                char = CharacterInfo(
                    name=char_data.get("name", ""),
                    role=char_data.get("role", "supporting"),
                    description=char_data.get("description", ""),
                    personality=char_data.get("personality", ""),
                    appearance=char_data.get("appearance", ""),
                    costume_hint=char_data.get("costume_hint", ""),
                    voice_style=char_data.get("voice_style", ""),
                )
                result.characters.append(char)

            # 解析分镜
            for scene_data in data.get("scenes", []):
                scene = SceneInfo(
                    scene_no=scene_data.get("scene_no", 1),
                    scene_title=scene_data.get("scene_title", ""),
                    description=scene_data.get("description", ""),
                    dialogue=scene_data.get("dialogue", ""),
                    camera_hint=scene_data.get("camera_hint", ""),
                    character_tags=scene_data.get("character_tags", []),
                    emotion=scene_data.get("emotion", ""),
                )
                result.scenes.append(scene)

            logger.info(
                f"Story generated: {result.title}, "
                f"{len(result.characters)} characters, {len(result.scenes)} scenes"
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise ValueError(f"LLM 返回格式错误，无法解析 JSON: {e}")
        except Exception as e:
            logger.error(f"Story generation failed: {e}")
            raise
