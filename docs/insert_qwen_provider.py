"""手动插入 qwen Provider"""
import psycopg2
import json

conn = psycopg2.connect(
    host="localhost",
    database="ylcraft",
    user="ylcraft",
    password="ylcraft_dev"
)
cur = conn.cursor()

cur.execute("SELECT provider_id FROM ai_provider_metadata WHERE provider_id = 'qwen'")
exists = cur.fetchone()

if not exists:
    cur.execute("""
        INSERT INTO ai_provider_metadata (
            provider_id, name, icon, color, description, base_url, api_format,
            supported_types, default_models, available_models, default_params,
            request_templates, response_configs, supported_sizes,
            reference_image_configs, parameter_transforms,
            is_active, is_editable, created_at, updated_at
        ) VALUES (
            'qwen', '阿里云百炼 (Qwen)', 'cloud', '#FF6A00', 
            '阿里云百炼 API，通义千问系列模型',
            'https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation',
            'custom', %s, %s, %s, %s, %s, %s, %s, %s,
            true, true, now(), now()
        )
    """, (
        json.dumps(["llm", "image"]),
        json.dumps({"llm": "qwen-plus", "image": "z-image-turbo"}),
        json.dumps({"image": ["z-image-turbo", "qwen-image-edit-plus", "qwen2.5-vl-32b-instruct"]}),
        json.dumps({"image": {"n": 1, "quality": "standard", "watermark": False, "prompt_extend": False}}),
        json.dumps({
            "image": '{\"model\": \"{{ model }}\", \"input\": {\"messages\": [{\"role\": \"user\", \"content\": [{\"image\": \"\"}, {\"image\": \"\"}, {\"text\": \"{{ prompt }}\"}]}]}, \"parameters\": {\"n\": 1, \"negative_prompt\": \"{{ negative_prompt }}\", \"prompt_extend\": {{ prompt_extend | default(false) }}, \"size\": \"{{ size }}\", \"watermark\": false}}'
        }),
        json.dumps({
            "image": '{\"images_path\": \"$.output.choices[*].message.content[*].image\", \"error_path\": \"$.message\", \"usage_path\": \"$.usage\", \"response_format\": \"url\"}'
        }),
        json.dumps({"image": ["1024x1024", "1152x896", "896x1152", "1024x1792", "1792x1024", "1280x1280"]}),
        json.dumps({
            "image": {
                "support_reference_image": True,
                "support_multiple_reference_images": True,
                "reference_image_field": "image",
                "reference_image_array_field": ""
            }
        }),
        json.dumps({"image": {"size": "{{ size.replace('x', '*') }}"}})
    ))
    print("Qwen Provider inserted successfully")
else:
    print("Qwen Provider already exists")

conn.commit()
cur.close()
conn.close()
