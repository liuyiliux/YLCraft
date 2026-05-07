/**
 * YLCraft — AI 剪辑页面
 *
 * 支持三种剪辑模式：
 * - CutClaw Agent：自然语言指令驱动，AI Agent 工具调用循环
 * - NarratoAI Pipeline：自动节拍踩点 + VLM 美学评分
 * - MoE 多专家协作：Beat / Composition / Narrative 三专家 + ControlPlane 仲裁
 */

import React, { useState, useCallback, useRef } from 'react'
import {
  Card,
  Tabs,
  Upload,
  Button,
  Input,
  Select,
  Slider,
  Progress,
  message,
  Space,
  Typography,
  Descriptions,
  List,
  Tag,
  Alert,
  Divider,
  Tooltip,
} from 'antd'
import {
  ScissorOutlined,
  UploadOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  ExperimentOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  DownloadOutlined,
  AudioOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import { startNarratoClip, startMoeClip, getClipTaskStatus, startCutClawClip, getCutClawTaskStatus } from '../../api'

const { Text, Title } = Typography
const { TextArea } = Input
const { Option } = Select

// =============================================================================
// 通用：视频上传组件
// =============================================================================

interface VideoUploadProps {
  value?: string
  onChange?: (path: string) => void
  label?: string
}

function VideoUpload({ value, onChange, label = '上传视频' }: VideoUploadProps) {
  const [uploading, setUploading] = useState(false)

  const beforeUpload = useCallback(async (file: File) => {
    const isVideo = file.type.startsWith('video/')
    if (!isVideo) {
      message.error('只能上传视频文件！')
      return false
    }
    const isLt500M = file.size / 1024 / 1024 < 500
    if (!isLt500M) {
      message.error('视频不能超过 500MB')
      return false
    }

    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch('/api/v1/clip-ops/upload', {
        method: 'POST',
        body: formData,
      }).then(r => r.json())

      if (res.success && res.output_path) {
        onChange?.(res.output_path)
        message.success('上传成功')
      } else {
        message.error(res.error || '上传失败')
      }
    } catch (e: any) {
      message.error('上传失败: ' + e.message)
    } finally {
      setUploading(false)
    }
    return false // 阻止自动上传
  }, [onChange])

  return (
    <Upload
      beforeUpload={beforeUpload}
      showUploadList={false}
      accept="video/*"
    >
      <Button icon={<UploadOutlined />} loading={uploading}>
        {label}
      </Button>
      {value && (
        <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
          已选: {value.split('/').pop()}
        </Text>
      )}
    </Upload>
  )
}

// =============================================================================
// 通用：任务轮询 Hook
// =============================================================================

interface TaskState {
  status: 'idle' | 'pending' | 'running' | 'done' | 'failed'
  progress: number
  progressMessage: string
  result: any
  error: string | null
  taskId: string | null
}

function useTaskPolling(fetchFn: (taskId: string) => Promise<any>) {
  const [state, setState] = useState<TaskState>({
    status: 'idle',
    progress: 0,
    progressMessage: '',
    result: null,
    error: null,
    taskId: null,
  })
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const start = useCallback(async (taskId: string) => {
    setState({
      status: 'pending',
      progress: 0,
      progressMessage: '任务已启动...',
      result: null,
      error: null,
      taskId,
    })

    intervalRef.current = setInterval(async () => {
      try {
        const res = await fetchFn(taskId)
        setState(prev => {
          const newStatus = res.status as TaskState['status']
          return {
            ...prev,
            status: newStatus,
            progress: res.progress ?? prev.progress,
            progressMessage: res.progress_message || res.progressMessage || '',
            result: res.result || prev.result,
            error: res.error || null,
          }
        })

        // 结束轮询
        if (res.status === 'done' || res.status === 'failed') {
          clearInterval(intervalRef.current!)
          intervalRef.current = null
          if (res.status === 'done') {
            message.success('剪辑完成！')
          }
        }
      } catch (e: any) {
        message.error('查询任务失败: ' + e.message)
        clearInterval(intervalRef.current!)
      }
    }, 2500)
  }, [fetchFn])

  const reset = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    setState({ status: 'idle', progress: 0, progressMessage: '', result: null, error: null, taskId: null })
  }, [])

  return { state, start, reset }
}

// =============================================================================
// Tab 1: CutClaw Agent
// =============================================================================

function CutClawTab() {
  const [videoPath, setVideoPath] = useState('')
  const [instruction, setInstruction] = useState('')
  const { state, start, reset } = useTaskPolling(getCutClawTaskStatus)

  const handleStart = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }
    try {
      const res = await startCutClawClip({
        video_path: videoPath,
        instruction: instruction || '请帮我剪辑出最精彩的片段，适合短视频分享',
      })
      if (res.success) {
        start(res.task_id)
        message.info('CutClaw Agent 开始分析...')
      } else {
        message.error(res.message || '启动失败')
      }
    } catch (e: any) {
      message.error('启动失败: ' + e.message)
    }
  }

  const isRunning = state.status === 'pending' || state.status === 'running'

  return (
    <Card
      type="inner"
      title={
        <span>
          <RobotOutlined style={{ marginRight: 8 }} />
          CutClaw Agent — AI 智能剪辑
        </span>
      }
    >
      <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="模式">LLM Agent 工具调用循环</Descriptions.Item>
        <Descriptions.Item label="核心能力">自然语言理解 → 视频分析 → 智能选段 → FFmpeg 执行</Descriptions.Item>
        <Descriptions.Item label="适合场景">指令模糊、需 AI 自主判断的复杂剪辑</Descriptions.Item>
      </Descriptions>

      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        {/* 视频上传 */}
        <div>
          <Text strong>1. 上传视频</Text>
          <div style={{ marginTop: 8 }}>
            <VideoUpload value={videoPath} onChange={setVideoPath} label="上传原始视频" />
          </div>
        </div>

        <Divider style={{ margin: '8px 0' }} />

        {/* 自然语言指令 */}
        <div>
          <Text strong>2. 输入剪辑指令</Text>
          <TextArea
            rows={3}
            placeholder="用自然语言描述你想要的剪辑效果，例如：
• 把最精彩的 30 秒剪出来
• 保留所有有人出现的片段
• 剪出适合抖音分享的卡点视频
• 去掉开头和结尾，中间内容精选"
            value={instruction}
            onChange={e => setInstruction(e.target.value)}
            style={{ marginTop: 8 }}
          />
        </div>

        {/* 操作按钮 */}
        <Space>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            disabled={isRunning || !videoPath}
            loading={isRunning}
          >
            {isRunning ? 'AI 分析中...' : '开始 CutClaw 剪辑'}
          </Button>
          {(state.status === 'done' || state.status === 'failed') && (
            <Button onClick={reset}>重置</Button>
          )}
        </Space>

        {/* 进度 */}
        {isRunning && (
          <div>
            <Progress percent={state.progress} status="active" />
            <Text type="secondary">{state.progressMessage}</Text>
          </div>
        )}

        {/* 结果 */}
        {state.status === 'done' && state.result && (
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            message="剪辑完成！"
            description={
              <div>
                <Text>{state.progressMessage}</Text>
                <br />
                {state.result.output_path && (
                  <Button
                    icon={<DownloadOutlined />}
                    href={`/api/v1/clip/download?file_path=${encodeURIComponent(state.result.output_path)}`}
                    style={{ marginTop: 8 }}
                  >
                    下载视频
                  </Button>
                )}
                {state.result.selected_clips?.length > 0 && (
                  <>
                    <Divider style={{ margin: '8px 0' }} />
                    <Text strong>AI 选段：</Text>
                    <List
                      size="small"
                      dataSource={state.result.selected_clips}
                      renderItem={(clip: any) => (
                        <List.Item>
                          <Tag color="blue">{clip.start?.toFixed(1)}s - {clip.end?.toFixed(1)}s</Tag>
                          <Text type="secondary">{clip.reason || clip.reason || ''}</Text>
                        </List.Item>
                      )}
                      style={{ marginTop: 8 }}
                    />
                  </>
                )}
              </div>
            }
          />
        )}

        {state.status === 'failed' && (
          <Alert type="error" message="剪辑失败" description={state.error || state.result?.message} />
        )}
      </Space>
    </Card>
  )
}

// =============================================================================
// Tab 2: NarratoAI Pipeline
// =============================================================================

function NarratoTab() {
  const [videoPath, setVideoPath] = useState('')
  const [targetDuration, setTargetDuration] = useState(60)
  const [numClips, setNumClips] = useState(5)
  const [minDuration, setMinDuration] = useState(3)
  const [maxDuration, setMaxDuration] = useState(15)
  const { state, start, reset } = useTaskPolling(getClipTaskStatus)

  const handleStart = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }
    try {
      const res = await startNarratoClip({
        video_path: videoPath,
        target_duration: targetDuration,
        num_clips: numClips,
        min_clip_duration: minDuration,
        max_clip_duration: maxDuration,
      })
      if (res.success) {
        start(res.task_id)
        message.info('NarratoAI Pipeline 开始执行...')
      } else {
        message.error(res.message || '启动失败')
      }
    } catch (e: any) {
      message.error('启动失败: ' + e.message)
    }
  }

  const isRunning = state.status === 'pending' || state.status === 'running'

  return (
    <Card
      type="inner"
      title={
        <span>
          <ThunderboltOutlined style={{ marginRight: 8 }} />
          NarratoAI Pipeline — 自动踩点剪辑
        </span>
      }
    >
      <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="模式">Pipeline 流水线</Descriptions.Item>
        <Descriptions.Item label="核心能力">OST 类型分类 → 音频节拍检测 → VLM 美学评分 → 智能选段合成</Descriptions.Item>
        <Descriptions.Item label="适合场景">BGM 视频踩点、节奏感强的短视频剪辑</Descriptions.Item>
      </Descriptions>

      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        {/* 视频上传 */}
        <div>
          <Text strong>1. 上传视频</Text>
          <div style={{ marginTop: 8 }}>
            <VideoUpload value={videoPath} onChange={setVideoPath} />
          </div>
        </div>

        <Divider style={{ margin: '8px 0' }} />

        {/* 剪辑参数 */}
        <div>
          <Text strong>2. 设置剪辑参数</Text>
          <div style={{ marginTop: 12 }}>
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <div>
                <Text>目标时长：{targetDuration} 秒</Text>
                <Slider
                  min={5} max={300} step={5}
                  value={targetDuration}
                  onChange={setTargetDuration}
                  marks={{ 30: '30s', 60: '60s', 120: '120s', 300: '5min' }}
                />
              </div>
              <div>
                <Text>目标片段数：{numClips}</Text>
                <Slider
                  min={1} max={20}
                  value={numClips}
                  onChange={setNumClips}
                />
              </div>
              <Space>
                <Text>最短片段：{minDuration}s</Text>
                <Text>最长片段：{maxDuration}s</Text>
              </Space>
              <Slider
                range
                min={1} max={30}
                value={[minDuration, maxDuration]}
                onChange={([min, max]) => { setMinDuration(min); setMaxDuration(max) }}
              />
            </Space>
          </div>
        </div>

        {/* 启动 */}
        <Space>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            disabled={isRunning || !videoPath}
            loading={isRunning}
          >
            {isRunning ? 'Pipeline 执行中...' : '开始 NarratoAI 剪辑'}
          </Button>
          {(state.status === 'done' || state.status === 'failed') && (
            <Button onClick={reset}>重置</Button>
          )}
        </Space>

        {/* 进度 */}
        {isRunning && (
          <div>
            <Progress percent={state.progress} status="active" />
            <Text type="secondary">{state.progressMessage}</Text>
          </div>
        )}

        {/* 结果 */}
        {state.status === 'done' && state.result && (
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            message="剪辑完成！"
            description={
              <div>
                <Space>
                  <Tag icon={<AudioOutlined />} color="purple">
                    OST 类型 {state.result.ost_type}
                  </Tag>
                  <Tag icon={<ThunderboltOutlined />} color="green">
                    硬件加速: {state.result.hwaccel_used}
                  </Tag>
                  <Text type="secondary">总时长 {state.result.total_duration?.toFixed(1)}s</Text>
                </Space>
                <br />
                {state.result.output_path && (
                  <Button
                    icon={<DownloadOutlined />}
                    href={`/api/v1/clip/download?file_path=${encodeURIComponent(state.result.output_path)}`}
                    style={{ marginTop: 8 }}
                  >
                    下载视频
                  </Button>
                )}
                {state.result.segments?.length > 0 && (
                  <>
                    <Divider style={{ margin: '8px 0' }} />
                    <Text strong>选段详情：</Text>
                    <List
                      size="small"
                      dataSource={state.result.segments}
                      renderItem={(seg: any) => (
                        <List.Item>
                          <Tag color="cyan">{seg.start?.toFixed(1)}s - {seg.end?.toFixed(1)}s</Tag>
                          <Tag color={seg.score > 7 ? 'green' : seg.score > 5 ? 'orange' : 'red'}>
                            评分 {seg.score?.toFixed(1)}
                          </Tag>
                          <Tag>{seg.source}</Tag>
                        </List.Item>
                      )}
                      style={{ marginTop: 8 }}
                    />
                  </>
                )}
              </div>
            }
          />
        )}

        {state.status === 'failed' && (
          <Alert type="error" message="剪辑失败" description={state.error} />
        )}
      </Space>
    </Card>
  )
}

// =============================================================================
// Tab 3: MoE 多专家协作
// =============================================================================

function MoETab() {
  const [videoPath, setVideoPath] = useState('')
  const [targetDuration, setTargetDuration] = useState(60)
  const { state, start, reset } = useTaskPolling(getClipTaskStatus)

  const handleStart = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }
    try {
      const res = await startMoeClip({
        video_path: videoPath,
        target_duration: targetDuration,
      })
      if (res.success) {
        start(res.task_id)
        message.info('MoE 多专家开始协作分析...')
      } else {
        message.error(res.message || '启动失败')
      }
    } catch (e: any) {
      message.error('启动失败: ' + e.message)
    }
  }

  const isRunning = state.status === 'pending' || state.status === 'running'

  return (
    <Card
      type="inner"
      title={
        <span>
          <ExperimentOutlined style={{ marginRight: 8 }} />
          MoE 多专家协作 — 三专家仲裁剪辑
        </span>
      }
    >
      <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="模式">MoE 多专家协作</Descriptions.Item>
        <Descriptions.Item label="专家">
          <Space>
            <Tag icon={<AudioOutlined />} color="purple">BeatExpert 节拍</Tag>
            <Tag icon={<PictureOutlined />} color="blue">CompositionExpert 构图</Tag>
            <Tag icon={<ScissorOutlined />} color="green">NarrativeExpert 叙事</Tag>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label="适合场景">高质量、多维度评估的精细化剪辑</Descriptions.Item>
      </Descriptions>

      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        {/* 视频上传 */}
        <div>
          <Text strong>1. 上传视频</Text>
          <div style={{ marginTop: 8 }}>
            <VideoUpload value={videoPath} onChange={setVideoPath} />
          </div>
        </div>

        <Divider style={{ margin: '8px 0' }} />

        {/* 参数 */}
        <div>
          <Text strong>2. 目标时长</Text>
          <div style={{ marginTop: 8 }}>
            <Slider
              min={5} max={300} step={5}
              value={targetDuration}
              onChange={setTargetDuration}
              marks={{ 30: '30s', 60: '60s', 120: '120s' }}
              style={{ width: 300 }}
            />
          </div>
        </div>

        {/* 启动 */}
        <Space>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            disabled={isRunning || !videoPath}
            loading={isRunning}
          >
            {isRunning ? '多专家协作中...' : '开始 MoE 协作剪辑'}
          </Button>
          {(state.status === 'done' || state.status === 'failed') && (
            <Button onClick={reset}>重置</Button>
          )}
        </Space>

        {/* 进度 */}
        {isRunning && (
          <div>
            <Progress percent={state.progress} status="active" />
            <Text type="secondary">{state.progressMessage}</Text>
          </div>
        )}

        {/* 结果 */}
        {state.status === 'done' && state.result && (
          <Alert
            type="success"
            showIcon
            icon={<CheckCircleOutlined />}
            message="MoE 剪辑完成！"
            description={
              <div>
                {state.result.expert_summary && (
                  <div style={{ marginBottom: 8 }}>
                    <Text strong>三专家分析结果：</Text>
                    <List
                      size="small"
                      dataSource={Object.entries(state.result.expert_summary)}
                      renderItem={([expert, info]: [string, any]) => (
                        <List.Item>
                          <Tag color="blue">{expert}</Tag>
                          <Text type="secondary">置信度 {(info.confidence * 100).toFixed(0)}%</Text>
                          <Text type="secondary" style={{ marginLeft: 8 }}>片段 {info.segments_found} 个</Text>
                        </List.Item>
                      )}
                      style={{ marginTop: 8 }}
                    />
                  </div>
                )}
                {state.result.output_path && (
                  <Button
                    icon={<DownloadOutlined />}
                    href={`/api/v1/clip/download?file_path=${encodeURIComponent(state.result.output_path)}`}
                    style={{ marginTop: 8 }}
                  >
                    下载视频
                  </Button>
                )}
                {state.result.segments?.length > 0 && (
                  <>
                    <Divider style={{ margin: '8px 0' }} />
                    <Text strong>最终选段：</Text>
                    <List
                      size="small"
                      dataSource={state.result.segments}
                      renderItem={(seg: any) => (
                        <List.Item>
                          <Tag color="green">{seg.start?.toFixed(1)}s - {seg.end?.toFixed(1)}s</Tag>
                          <Tag color="geekblue">{seg.source_expert}</Tag>
                          <Text type="secondary">{seg.reason}</Text>
                        </List.Item>
                      )}
                      style={{ marginTop: 8 }}
                    />
                  </>
                )}
              </div>
            }
          />
        )}

        {state.status === 'failed' && (
          <Alert type="error" message="剪辑失败" description={state.error} />
        )}
      </Space>
    </Card>
  )
}

// =============================================================================
// 主页面
// =============================================================================

export default function ClipLabPage() {
  return (
    <div>
      <Card
        title={
          <span>
            <ScissorOutlined style={{ marginRight: 8 }} />
            AI 剪辑 — AI 视频剪辑
          </span>
        }
        style={{ marginBottom: 16 }}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            三种剪辑模式：按需选择
          </Text>
        }
      >
        <Alert
          message="💡 选择建议"
          description={
            <Space>
              <Text>模糊指令 → CutClaw Agent</Text>
              <Text>|</Text>
              <Text>BGM 踩点 → NarratoAI Pipeline</Text>
              <Text>|</Text>
              <Text>高质量多维评估 → MoE 多专家</Text>
            </Space>
          }
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Tabs
          items={[
            {
              key: 'cutclaw',
              label: '🤖 CutClaw Agent',
              children: <CutClawTab />,
            },
            {
              key: 'narrato',
              label: '🎵 NarratoAI Pipeline',
              children: <NarratoTab />,
            },
            {
              key: 'moe',
              label: '🔬 MoE 多专家协作',
              children: <MoETab />,
            },
          ]}
        />
      </Card>
    </div>
  )
}
