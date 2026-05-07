import React, { useState } from "react";
import {
  Card,
  Button,
  Input,
  Select,
  Row,
  Col,
  Tag,
  Steps,
  message,
  Spin,
  Typography,
  Divider,
  Space,
  Badge,
  Tooltip,
  Alert,
} from "antd";
import {
  PlayCircleOutlined,
  SaveOutlined,
  PictureOutlined,
  EyeOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import {
  generateStory,
  saveStoryCharacters,
  generateStoryPortrait,
  getStory,
} from "../../api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const StoryMaker: React.FC = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);

  // Step 1: 输入
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("short_drama");
  const [numScenes, setNumScenes] = useState(8);

  // Step 2: 生成结果
  const [storyId, setStoryId] = useState<string | null>(null);
  const [storyData, setStoryData] = useState<any>(null);
  const [savingCharacters, setSavingCharacters] = useState(false);
  const [generatingPortraits, setGeneratingPortraits] = useState<Set<string>>(new Set());

  // Step 3: 完成
  const [completed, setCompleted] = useState(false);

  // 风格选项
  const styleOptions = [
    { label: "都市短剧", value: "short_drama" },
    { label: "二次元漫剧", value: "manga" },
  ];

  // 场景数量选项
  const sceneOptions = [
    { label: "4 个分镜", value: 4 },
    { label: "6 个分镜", value: 6 },
    { label: "8 个分镜", value: 8 },
    { label: "10 个分镜", value: 10 },
    { label: "12 个分镜", value: 12 },
  ];

  // Step 1: 生成故事
  const handleGenerate = async () => {
    if (!topic.trim()) {
      message.warning("请输入创作主题");
      return;
    }

    setLoading(true);
    try {
      const response = await generateStory({
        topic: topic.trim(),
        style,
        num_scenes: numScenes,
      });

      if (response.success) {
        setStoryId(response.story_id);
        setStoryData(response.data);
        setCurrentStep(1);
        message.success("故事生成成功！");
      } else {
        message.error(response.message || "生成失败");
      }
    } catch (error: any) {
      message.error(error?.message || "生成失败，请重试");
      console.error("Story generate error:", error);
    } finally {
      setLoading(false);
    }
  };

  // 保存角色到角色库
  const handleSaveCharacters = async () => {
    if (!storyData?.characters) return;

    setSavingCharacters(true);
    try {
      const response = await saveStoryCharacters({
        story_id: storyId,
        characters: storyData.characters,
        save_to_library: true,
      });

      if (response.success) {
        message.success(response.message);
      }
    } catch (error: any) {
      message.error("保存角色失败");
    } finally {
      setSavingCharacters(false);
    }
  };

  // 生成角色肖像
  const handleGeneratePortrait = async (character: any) => {
    if (!storyId) return;

    setGeneratingPortraits((prev) => new Set([...prev, character.name]));
    try {
      const response = await generateStoryPortrait({
        story_id: storyId,
        character_name: character.name,
        appearance: character.appearance,
        costume_hint: character.costume_hint,
        style_hint: storyData?.style_hint || "",
        generate_multi_view: true,
      });

      if (response.success) {
        message.success(`已生成 ${character.name} 的肖像`);
        // 刷新数据
        fetchStoryDetail();
      }
    } catch (error: any) {
      message.error(`生成 ${character.name} 肖像失败`);
    } finally {
      setGeneratingPortraits((prev) => {
        const next = new Set(prev);
        next.delete(character.name);
        return next;
      });
    }
  };

  const fetchStoryDetail = async () => {
    if (!storyId) return;
    try {
      const response = await getStory(storyId);
      if (response.success) {
        setStoryData(response);
      }
    } catch (error) {
      console.error("Fetch story detail error:", error);
    }
  };

  // 完成
  const handleComplete = () => {
    setCompleted(true);
    setCurrentStep(2);
    message.success("Story Maker 完成！");
  };

  // 重置
  const handleReset = () => {
    setCurrentStep(0);
    setStoryId(null);
    setStoryData(null);
    setCompleted(false);
    setTopic("");
    setStyle("short_drama");
    setNumScenes(8);
  };

  // 角色类型标签颜色
  const getRoleColor = (role: string) => {
    const colors: Record<string, string> = {
      protagonist: "red",
      antagonist: "orange",
      supporting: "blue",
      extra: "default",
    };
    return colors[role] || "default";
  };

  // 角色类型中文
  const getRoleText = (role: string) => {
    const texts: Record<string, string> = {
      protagonist: "主角",
      antagonist: "反派",
      supporting: "配角",
      extra: "龙套",
    };
    return texts[role] || role;
  };

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>
          <VideoCameraOutlined style={{ marginRight: 12 }} />
          Story Maker — AI 短剧漫剧生成
        </Title>
        <Text type="secondary">输入主题，AI 自动生成故事、角色、分镜脚本</Text>
      </div>

      <Steps
        current={currentStep}
        items={[
          {
            title: "输入主题",
            description: "设定创作方向",
          },
          {
            title: "生成结果",
            description: "角色与分镜",
          },
          {
            title: "完成",
            description: "素材确认",
          },
        ]}
        style={{ marginBottom: 32 }}
      />

      {/* Step 1: 输入创作主题 */}
      {currentStep === 0 && (
        <Card
          title="创作主题设定"
          style={{ maxWidth: 800, margin: "0 auto" }}
        >
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <div>
              <Text strong>创作主题</Text>
              <TextArea
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="例如：都市爱情短剧，讲述一个程序员和设计师的爱情故事..."
                autoSize={{ minRows: 4, maxRows: 8 }}
                style={{ marginTop: 8 }}
              />
            </div>

            <Row gutter={16}>
              <Col span={12}>
                <Text strong>风格选择</Text>
                <Select
                  value={style}
                  onChange={setStyle}
                  options={styleOptions}
                  style={{ width: "100%", marginTop: 8 }}
                />
              </Col>
              <Col span={12}>
                <Text strong>分镜数量</Text>
                <Select
                  value={numScenes}
                  onChange={setNumScenes}
                  options={sceneOptions}
                  style={{ width: "100%", marginTop: 8 }}
                />
              </Col>
            </Row>

            <Alert
              message="提示"
              description={
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  <li>输入清晰的主题，AI 会生成完整的故事结构</li>
                  <li>都市短剧风格偏向现实主义，二次元漫剧偏向动漫风格</li>
                  <li>生成后可保存角色到角色库，并生成角色肖像</li>
                </ul>
              }
              type="info"
              showIcon
            />

            <Button
              type="primary"
              size="large"
              icon={<PlayCircleOutlined />}
              onClick={handleGenerate}
              loading={loading}
              block
            >
              开始创作
            </Button>
          </Space>
        </Card>
      )}

      {/* Step 2: 生成结果展示 */}
      {currentStep === 1 && storyData && (
        <Spin spinning={loading}>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Button
                icon={<SaveOutlined />}
                onClick={handleSaveCharacters}
                loading={savingCharacters}
              >
                保存所有角色到角色库
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleReset}>
                重新创作
              </Button>
            </Space>
          </div>

          {/* 故事信息 */}
          <Card
            title={
              <span>
                <VideoCameraOutlined style={{ marginRight: 8 }} />
                {storyData.title || "生成的故事"}
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            <Paragraph>
              <Text strong>故事大纲：</Text>
              <br />
              {storyData.plot_outline}
            </Paragraph>
            {storyData.style_hint && (
              <Paragraph>
                <Text strong>视觉风格：</Text>
                <br />
                <Tag color="purple">{storyData.style_hint}</Tag>
              </Paragraph>
            )}
          </Card>

          <Row gutter={[16, 16]}>
            {/* 左侧：角色列表 */}
            <Col span={10}>
              <Card
                title={
                  <span>
                    <UserOutlined style={{ marginRight: 8 }} />
                    角色列表 ({storyData.characters?.length || 0})
                  </span>
                }
              >
                <div
                  style={{
                    maxHeight: 600,
                    overflowY: "auto",
                    paddingRight: 8,
                  }}
                >
                  {storyData.characters?.map(
                    (char: any, index: number) => (
                      <Card
                        key={index}
                        size="small"
                        style={{ marginBottom: 12 }}
                        hoverable
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 8,
                          }}
                        >
                          <Space>
                            <Text strong>{char.name}</Text>
                            <Tag
                              color={getRoleColor(char.role)}
                            >
                              {getRoleText(char.role)}
                            </Tag>
                          </Space>
                          <Tooltip title="生成肖像">
                            <Button
                              type="primary"
                              size="small"
                              icon={<PictureOutlined />}
                              loading={generatingPortraits.has(
                                char.name
                              )}
                              onClick={() =>
                                handleGeneratePortrait(char)
                              }
                            >
                              生肖像
                            </Button>
                          </Tooltip>
                        </div>

                        {char.appearance && (
                          <Paragraph
                            type="secondary"
                            style={{ fontSize: 12, marginBottom: 4 }}
                          >
                            <Text strong>外貌：</Text>
                            {char.appearance}
                          </Paragraph>
                        )}

                        {char.personality && (
                          <Paragraph
                            type="secondary"
                            style={{ fontSize: 12, marginBottom: 4 }}
                          >
                            <Text strong>性格：</Text>
                            {char.personality}
                          </Paragraph>
                        )}

                        {/* 显示已生成的肖像 */}
                        {storyData.portraits?.[char.name]
                          ?.portrait_urls?.length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <Text
                              type="secondary"
                              style={{ fontSize: 11 }}
                            >
                              已生成肖像：
                            </Text>
                            <div
                              style={{
                                display: "flex",
                                gap: 4,
                                marginTop: 4,
                                overflowX: "auto",
                              }}
                            >
                              {storyData.portraits[
                                char.name
                              ].portrait_urls.map(
                                (url: string, i: number) => (
                                  <img
                                    key={i}
                                    src={url}
                                    alt={`${char.name} ${i + 1}`}
                                    style={{
                                      width: 60,
                                      height: 80,
                                      objectFit: "cover",
                                      borderRadius: 4,
                                    }}
                                  />
                                )
                              )}
                            </div>
                          </div>
                        )}
                      </Card>
                    )
                  )}
                </div>
              </Card>
            </Col>

            {/* 右侧：分镜脚本 */}
            <Col span={14}>
              <Card
                title={
                  <span>
                    <VideoCameraOutlined style={{ marginRight: 8 }} />
                    分镜脚本 ({storyData.scenes?.length || 0}{" "}
                    场)
                  </span>
                }
              >
                <div
                  style={{
                    maxHeight: 600,
                    overflowY: "auto",
                    paddingRight: 8,
                  }}
                >
                  {storyData.scenes?.map((scene: any, index: number) => (
                    <Card
                      key={index}
                      size="small"
                      style={{ marginBottom: 12 }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          marginBottom: 8,
                        }}
                      >
                        <Space>
                          <Badge
                            count={`第 ${scene.scene_no} 场`}
                            style={{
                              backgroundColor: "#1890ff",
                            }}
                          />
                          {scene.scene_title && (
                            <Text strong>{scene.scene_title}</Text>
                          )}
                        </Space>
                        {scene.emotion && (
                          <Tag color="orange">{scene.emotion}</Tag>
                        )}
                      </div>

                      {scene.description && (
                        <Paragraph style={{ marginBottom: 4 }}>
                          {scene.description}
                        </Paragraph>
                      )}

                      {scene.dialogue && (
                        <Paragraph
                          type="secondary"
                          style={{ fontSize: 12, marginBottom: 4 }}
                        >
                          <Text strong>对白：</Text>
                          {scene.dialogue}
                        </Paragraph>
                      )}

                      <div style={{ marginTop: 4 }}>
                        {scene.camera_hint && (
                          <Tag color="blue">{scene.camera_hint}</Tag>
                        )}
                        {scene.character_tags?.map(
                          (tag: string) => (
                            <Tag key={tag}>{tag}</Tag>
                          )
                        )}
                      </div>
                    </Card>
                  ))}
                </div>
              </Card>
            </Col>
          </Row>

          <div style={{ marginTop: 16, textAlign: "center" }}>
            <Button
              type="primary"
              size="large"
              icon={<CheckCircleOutlined />}
              onClick={handleComplete}
            >
              完成创作
            </Button>
          </div>
        </Spin>
      )}

      {/* Step 3: 完成 */}
      {currentStep === 2 && (
        <Card
          title="🎉 创作完成！"
          style={{ maxWidth: 800, margin: "0 auto" }}
        >
          <Alert
            message="Story Maker 创作流程已完成"
            description={
              <div>
                <p>✅ 故事已生成并保存到数据库</p>
                <p>✅ 角色可保存到角色库</p>
                <p>✅ 角色肖像已生成</p>
                <p>下一步：前往「角色库」管理角色，或「AI 剪辑」开始剪辑</p>
              </div>
            }
            type="success"
            showIcon
            style={{ marginBottom: 24 }}
          />

          <div style={{ textAlign: "center" }}>
            <Space size="large">
              <Button
                type="primary"
                size="large"
                onClick={() =>
                  (window.location.href = "/characters")
                }
              >
                前往角色库
              </Button>
              <Button
                size="large"
                onClick={() =>
                  (window.location.href = "/clip")
                }
              >
                前往 AI 剪辑
              </Button>
              <Button
                icon={<ReloadOutlined />}
                size="large"
                onClick={handleReset}
              >
                再创作一个
              </Button>
            </Space>
          </div>
        </Card>
      )}
    </div>
  );
};

export default StoryMaker;
