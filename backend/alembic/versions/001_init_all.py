"""init all tables — merged migration

将所有表、索引、触发器、默认数据合并到一个迁移中，
替换原来 7 个零散的增量迁移脚本。

Revision ID: 001
Revises: None
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =============================================================================
# Default provider metadata — 系统内置服务商配置
# =============================================================================

DEFAULT_PROVIDERS = [
    {
        "provider_id": "openai",
        "name": "OpenAI",
        "icon": "brain",
        "color": "#10a37f",
        "description": "OpenAI GPT-4、DALL-E、Whisper 等",
        "base_url": "https://api.openai.com/v1",
        "api_format": "openai-compatible",
        "supported_types": '["llm", "image", "tts", "stt", "embedding"]',
        "default_models": '{"llm": "gpt-4o", "image": "dall-e-3", "tts": "tts-1", "stt": "whisper-1", "embedding": "text-embedding-3-small"}',
        "available_models": '{}',
        "default_params": '{"llm": {"temperature": 0.7, "max_tokens": 4096}, "image": {"size": "1024x1024", "quality": "standard"}, "tts": {"voice": "alloy", "speed": 1.0}}',
        "request_templates": '{}',
        "response_configs": '{}',
        "supported_sizes": '{}',
        "reference_image_configs": '{}',
        "parameter_transforms": '{}',
        "is_editable": True,
    },
    {
        "provider_id": "siliconflow",
        "name": "硅基流动 (SiliconFlow)",
        "icon": "cloud",
        "color": "#00d4aa",
        "description": "硅基流动 API，支持多种开源模型",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_format": "openai-compatible",
        "supported_types": '["llm", "image", "embedding"]',
        "default_models": '{"llm": "Qwen/Qwen3-VL-32B-Instruct", "image": "Kwai-Kolors/Kolors", "embedding": "BAAI/bge-m3"}',
        "available_models": '{"llm": ["Qwen/Qwen3-VL-32B-Instruct", "Qwen/QwQ-32B", "tencent/Hunyuan-MT-7B"], "image": ["Qwen/Qwen-Image-Edit", "Kwai-Kolors/Kolors", "black-forest-labs/FLUX.1-schnell"]}',
        "default_params": '{"llm": {"temperature": 0.7, "max_tokens": 8192}, "image": {"n": 1, "quality": "standard", "watermark": false, "prompt_extend": false}}',
        "request_templates": '{"image": "{\\"model\\": \\"{{ model }}\\", \\"prompt\\": \\"{{ prompt }}\\", \\"image1\\": \\"\\", \\"num_inference_steps\\": {{ num_inference_steps | default(20) }}, \\"guidance_scale\\": {{ guidance_scale | default(4) }}, \\"n\\": {{ n | default(1) }}}"}',
        "response_configs": '{"image": "{\\"images_path\\": \\"$.images[*].url\\", \\"error_path\\": \\"$.error.message\\", \\"usage_path\\": \\"$.usage\\", \\"response_format\\": \\"url\\"}"}',
        "supported_sizes": '{"image": ["1024x1024", "768x1344", "1344x768", "1328x1328", "1664x928", "928x1664"]}',
        "reference_image_configs": '{"image": {"support_reference_image": true, "support_multiple_reference_images": false, "reference_image_field": "image1", "reference_image_array_field": ""}}',
        "parameter_transforms": '{}',
        "is_editable": True,
    },
    {
        "provider_id": "qwen",
        "name": "阿里云百炼 (Qwen)",
        "icon": "cloud",
        "color": "#FF6A00",
        "description": "阿里云百炼 API，通义千问系列模型",
        "base_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        "api_format": "custom",
        "supported_types": '["llm", "image"]',
        "default_models": '{"llm": "qwen-plus", "image": "z-image-turbo"}',
        "available_models": '{"image": ["z-image-turbo", "qwen-image-edit-plus", "qwen2.5-vl-32b-instruct"]}',
        "default_params": '{"image": {"n": 1, "quality": "standard", "watermark": false, "prompt_extend": false}}',
        "request_templates": '{"image": "{\\"model\\": \\"{{ model }}\\", \\"input\\": {\\"messages\\": [{\\"role\\": \\"user\\", \\"content\\": [{\\"image\\": \\"\\"}, {\\"image\\": \\"\\"}, {\\"text\\": \\"{{ prompt }}\\"}]}]}, \\"parameters\\": {\\"n\\": 1, \\"negative_prompt\\": \\"{{ negative_prompt }}\\", \\"prompt_extend\\": {{ prompt_extend | default(false) }}, \\"size\\": \\"{{ size }}\\", \\"watermark\\": false}}"}',
        "response_configs": '{"image": "{\\"images_path\\": \\"$.output.choices[*].message.content[*].image\\", \\"error_path\\": \\"$.message\\", \\"usage_path\\": \\"$.usage\\", \\"response_format\\": \\"url\\"}"}',
        "supported_sizes": '{"image": ["1024x1024", "1152x896", "896x1152", "1024x1792", "1792x1024", "1280x1280"]}',
        "reference_image_configs": '{"image": {"support_reference_image": true, "support_multiple_reference_images": true, "reference_image_field": "image", "reference_image_array_field": ""}}',
        "parameter_transforms": '{"image": "{\\"size\\": \\"{{ size.replace(\'x\', \'*\') }}\\""}',
        "is_editable": True,
    },
    {
        "provider_id": "gemini",
        "name": "Google Gemini",
        "icon": "globe",
        "color": "#4285f4",
        "description": "Google Gemini 多模态模型",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_format": "gemini",
        "supported_types": '["llm", "image"]',
        "default_models": '{"llm": "gemini-2.0-flash", "image": "gemini-2.5-flash-image"}',
        "available_models": '{}',
        "default_params": '{"llm": {"temperature": 0.9, "max_tokens": 8192}}',
        "request_templates": '{}',
        "response_configs": '{}',
        "supported_sizes": '{}',
        "reference_image_configs": '{}',
        "parameter_transforms": '{}',
        "is_editable": True,
    },
    {
        "provider_id": "generic",
        "name": "通用配置",
        "icon": "settings",
        "color": "#94a3b8",
        "description": "通用 OpenAI 兼容 API 配置",
        "base_url": None,
        "api_format": "custom",
        "supported_types": '["llm", "image", "video", "tts", "stt", "embedding"]',
        "default_models": '{}',
        "available_models": '{}',
        "default_params": '{}',
        "request_templates": '{}',
        "response_configs": '{}',
        "supported_sizes": '{}',
        "reference_image_configs": '{}',
        "parameter_transforms": '{}',
        "is_editable": True,
    },
]


def upgrade() -> None:
    # ========================================================================
    # 1. AI 连接器表（原来由 create_all 创建，现纳入迁移统一管理）
    # ========================================================================

    op.create_table(
        'ai_connectors',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), server_default=''),
        sa.Column('provider_type', sa.String(), nullable=False, server_default='llm'),
        sa.Column('base_url', sa.String(), nullable=True),
        sa.Column('api_endpoint', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(), nullable=True),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('default_model', sa.String(), server_default='gpt-4o'),
        sa.Column('available_models', sa.String(), server_default='[]'),
        sa.Column('max_tokens', sa.Integer(), server_default='4096'),
        sa.Column('temperature', sa.Float(), server_default='0.7'),
        sa.Column('request_template', sa.Text(), nullable=True),
        sa.Column('response_config', sa.Text(), nullable=True),
        sa.Column('parameter_transforms', sa.Text(), nullable=True),
        sa.Column('supported_sizes', sa.Text(), nullable=True),
        sa.Column('default_params', sa.Text(), nullable=True),
        sa.Column('support_reference_image', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('support_multiple_reference_images', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('reference_image_field', sa.String(), server_default='image'),
        sa.Column('reference_image_array_field', sa.String(), nullable=True),
        sa.Column('embedding_type', sa.String(), nullable=True),
        sa.Column('embedding_dimension', sa.Integer(), nullable=True),
        sa.Column('normalize_embeddings', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('support_vision_input', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('test_prompt', sa.Text(), nullable=True),
        sa.Column('monthly_budget', sa.Float(), nullable=True),
        sa.Column('daily_limit', sa.Integer(), nullable=True),
        sa.Column('price_per_call', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0'),
        sa.Column('total_cost', sa.Float(), server_default='0.0'),
        sa.Column('api_format', sa.String(36), nullable=False, server_default='custom'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'ai_usage_logs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('connector_id', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), server_default='0'),
        sa.Column('total_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost', sa.Float(), server_default='0.0'),
        sa.Column('latency_ms', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(), server_default='success'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # ========================================================================
    # 2. AI Provider 元数据表（最终 schema：已移除废弃的 request_template 单数）
    # ========================================================================

    op.create_table(
        'ai_provider_metadata',
        sa.Column('provider_id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('icon', sa.String(50), server_default='brain'),
        sa.Column('color', sa.String(20), server_default='#94a3b8'),
        sa.Column('description', sa.String(500), server_default=''),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('api_key', sa.String(500), nullable=True),
        sa.Column('api_format', sa.String(50), server_default='openai-compatible'),
        sa.Column('supported_types', sa.Text(), server_default='[]'),
        sa.Column('default_models', sa.Text(), server_default='{}'),
        sa.Column('available_models', sa.Text(), server_default='{}'),
        sa.Column('default_params', sa.Text(), server_default='{}'),
        sa.Column('request_templates', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('response_configs', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('supported_sizes', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('reference_image_configs', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('parameter_transforms', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('is_editable', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # ========================================================================
    # 3. 资产中枢核心表
    # ========================================================================

    op.create_table(
        'asset_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('asset_type', sa.String(), nullable=False, index=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=True, index=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, server_default='{}'),
        sa.Column('tags_json', postgresql.JSONB, server_default='[]'),
        sa.Column('use_count', sa.Integer(), server_default='0', index=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('phash', sa.String(), nullable=True, index=True),
        sa.Column('fulltext_vector', postgresql.TSVECTOR(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'asset_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('version_number', sa.Integer(), nullable=False, index=True),
        sa.Column('prompt_used', sa.Text(), nullable=True),
        sa.Column('model_used', sa.String(), nullable=True),
        sa.Column('params_json', postgresql.JSONB, server_default='{}'),
        sa.Column('lineage_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )

    op.create_table(
        'asset_representations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_version_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_versions.id'), nullable=False, index=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('extra_json', postgresql.JSONB, server_default='{}'),
    )

    op.create_table(
        'asset_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, unique=True, index=True),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.Column('embedding_model', sa.String(), server_default='paraphrase-multilingual-MiniLM-L12-v2'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'asset_relations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('target_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('relation_type', sa.String(), nullable=False, index=True),
        sa.Column('context_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tags.id'), nullable=True, index=True),
        sa.Column('level', sa.Integer(), server_default='0', index=True),
        sa.Column('path', sa.String(), nullable=False, index=True),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True, index=True),
        sa.Column('asset_count', sa.Integer(), server_default='0', index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'asset_tag_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('tag_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('tags.id'), nullable=False, index=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('source', sa.String(), server_default='manual'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'ai_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_node_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('model_type', sa.String(), nullable=False, index=True),
        sa.Column('base_model', sa.String(), nullable=False, index=True),
        sa.Column('file_hash', sa.String(), nullable=False, index=True),
        sa.Column('civitai_model_id', sa.String(), server_default='', index=True),
        sa.Column('civitai_version_id', sa.String(), server_default=''),
        sa.Column('trigger_words', sa.String(), server_default=''),
        sa.Column('recommended_weight', sa.Float(), server_default='1.0'),
        sa.Column('training_resolution', sa.String(), server_default=''),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), server_default='0'),
        sa.Column('preview_urls', sa.Text(), server_default='[]'),
    )

    # ========================================================================
    # 4. 向量搜索辅助表
    # ========================================================================

    op.create_table(
        'asset_search_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('query_hash', sa.String(64), nullable=False, index=True),
        sa.Column('result_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('total_count', sa.Integer(), server_default='0'),
        sa.Column('params_json', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'search_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('query_text', sa.Text(), nullable=True),
        sa.Column('query_vector_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('result_count', sa.Integer(), server_default='0'),
        sa.Column('filters_json', postgresql.JSONB, server_default='{}'),
        sa.Column('search_type', sa.String(), server_default='hybrid'),
        sa.Column('user_id', sa.String(), nullable=True, index=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'similar_asset_pairs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('asset_a_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('asset_b_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('asset_nodes.id'), nullable=False, index=True),
        sa.Column('similarity_score', sa.Float(), nullable=False, index=True),
        sa.Column('embedding_type', sa.String(), server_default='image'),
        sa.Column('computed_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # ========================================================================
    # 5. 性能索引
    # ========================================================================

    # --- 向量索引 ---
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_embeddings_embedding_hnsw
        ON asset_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_embeddings_embedding_ivfflat
        ON asset_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)

    # --- 全文搜索索引 ---
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_asset_nodes_fulltext
        ON asset_nodes
        USING gin (fulltext_vector);
    """)

    # --- asset_nodes B-tree 索引 ---
    op.create_index(
        'idx_asset_nodes_created_desc',
        'asset_nodes',
        ['created_at'],
        postgresql_where=sa.text('created_at IS NOT NULL'),
    )
    op.create_index(
        'idx_asset_nodes_quality_score',
        'asset_nodes',
        ['quality_score'],
        postgresql_where=sa.text('quality_score IS NOT NULL'),
    )

    # --- asset_versions 复合索引 ---
    op.create_index(
        'idx_asset_versions_asset_node_created',
        'asset_versions',
        ['asset_node_id', 'created_at'],
    )

    # --- asset_relations 复合索引 ---
    op.create_index(
        'idx_asset_relations_source_type',
        'asset_relations',
        ['source_id', 'relation_type'],
    )
    op.create_index(
        'idx_asset_relations_target_type',
        'asset_relations',
        ['target_id', 'relation_type'],
    )

    # --- similar_asset_pairs 索引 ---
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_score
        ON similar_asset_pairs (similarity_score DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_a
        ON similar_asset_pairs (asset_a_id, similarity_score DESC);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_similar_pairs_b
        ON similar_asset_pairs (asset_b_id, similarity_score DESC);
    """)

    # --- tags 复合索引 ---
    op.create_index(
        'idx_tags_category_asset_count',
        'tags',
        ['category', 'asset_count'],
    )

    # ========================================================================
    # 6. 自动更新 updated_at 触发器
    # ========================================================================

    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS update_asset_nodes_updated_at ON asset_nodes;
        CREATE TRIGGER update_asset_nodes_updated_at
            BEFORE UPDATE ON asset_nodes
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    """)
    op.execute("COMMENT ON COLUMN asset_nodes.updated_at IS '自动更新触发器';")

    # ========================================================================
    # 7. 默认 Provider 元数据
    # ========================================================================

    provider_table = sa.table(
        'ai_provider_metadata',
        sa.column('provider_id', sa.String),
        sa.column('name', sa.String),
        sa.column('icon', sa.String),
        sa.column('color', sa.String),
        sa.column('description', sa.String),
        sa.column('base_url', sa.String),
        sa.column('api_format', sa.String),
        sa.column('supported_types', sa.Text),
        sa.column('default_models', sa.Text),
        sa.column('available_models', sa.Text),
        sa.column('default_params', sa.Text),
        sa.column('request_templates', sa.Text),
        sa.column('response_configs', sa.Text),
        sa.column('supported_sizes', sa.Text),
        sa.column('reference_image_configs', sa.Text),
        sa.column('parameter_transforms', sa.Text),
        sa.column('is_editable', sa.Boolean),
    )

    op.bulk_insert(provider_table, DEFAULT_PROVIDERS)


def downgrade() -> None:
    """回滚：按依赖顺序删除所有表和对象"""
    # 触发器 & 函数
    op.execute("DROP TRIGGER IF EXISTS update_asset_nodes_updated_at ON asset_nodes;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # 辅助表
    op.drop_table('similar_asset_pairs')
    op.drop_table('search_history')
    op.drop_table('asset_search_cache')

    # 资产核心表（先删除依赖表）
    op.drop_table('ai_models')
    op.drop_table('asset_tag_links')
    op.drop_table('tags')
    op.drop_table('asset_relations')
    op.drop_table('asset_embeddings')
    op.drop_table('asset_representations')
    op.drop_table('asset_versions')
    op.drop_table('asset_nodes')

    # AI 元数据 & 连接器
    op.drop_table('ai_provider_metadata')
    op.drop_table('ai_usage_logs')
    op.drop_table('ai_connectors')
