/**
 * YLCraft — BGM 配乐页面
 *
 * 功能：
 * 1. BGM 库：按风格/情绪浏览，<audio> 预览播放，收藏
 * 2. 混音面板：选择视频 + 选择 BGM → 调节参数 → 混音
 * 3. 自定义上传：上传自己的 BGM
 */

import { useState, useEffect, useRef } from 'react'
import {
  Card, Row, Col, Input, Select, Button, Space, Spin, message,
  Tag, Progress, Typography, Tabs, Upload, Modal, Form,
  Slider, Switch, Badge, Empty, Tooltip, InputNumber,
} from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, PlusOutlined,
  HeartOutlined, HeartFilled, DeleteOutlined,
  UploadOutlined, SoundOutlined, ThunderboltOutlined,
  SyncOutlined, CheckCircleOutlined, LoadingOutlined,
  CloseCircleOutlined, CustomerServiceOutlined,
} from '@ant-design/icons'
import {
  listBGMLibrary, listBGMGenres, listBGMMoods,
  getBGMFileUrl, uploadBGM, mixBGM, getBGMMixTask,
  toggleBGMFavorite, deleteBGMTrack,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Text, Title, Paragraph } = Typography
const { Option } = Select

// 风格颜色映射
const GENRE_COLORS: Record<string, string> = {
  upbeat: '#ff6b35',
  calm: '#48cae4',
  epic: '#e63946',
  ambient: '#8ecae6',
  cinematic: '#6c757d',
  jazz: '#f4a261',
  other: '#adb5bd',
}

const GENRE_ICONS: Record<string, string> = {
  upbeat: '⚡',
  calm: '🌊',
  epic: '🔥',
  ambient: '🌙',
  cinematic: '🎬',
  jazz: '🎷',
  other: '🎵',
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '等待中', color: 'default' },
  running: { label: '混音中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

export default function BGMPage() {
  const { theme: THEME } = useTheme()
  const [tracks, setTracks] = useState<any[]>([])
  const [genres, setGenres] = useState<string[]>([])
  const [moods, setMoods] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [filterGenre, setFilterGenre] = useState<string | undefined>()
  const [filterMood, setFilterMood] = useState<string | undefined>()
  const [searchText, setSearchText] = useState('')
  const [selectedTrack, setSelectedTrack] = useState<any>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)

  // 混音参数
  const [videoPath, setVideoPath] = useState('')
  const [bgmVolume, setBgmVolume] = useState(0.3)
  const [originalVolume, setOriginalVolume] = useState(1.0)
  const [fadeIn, setFadeIn] = useState(0)
  const [fadeOut, setFadeOut] = useState(2)
  const [loopBGM, setLoopBGM] = useState(true)
  const [mixTasks, setMixTasks] = useState<any[]>([])
  const [mixing, setMixing] = useState(false)

  // 上传
  const [uploadModal, setUploadModal] = useState(false)
  const [uploadForm] = Form.useForm()
  const [uploading, setUploading] = useState(false)

  const audioRef = useRef<HTMLAudioElement>(null)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    loadLibrary()
    loadGenres()
    loadMoods()
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
      audioRef.current?.pause()
    }
  }, [])

  useEffect(() => {
    loadLibrary()
  }, [filterGenre, filterMood, searchText])

  const loadLibrary = async () => {
    setLoading(true)
    try {
      const res = await listBGMLibrary({
        genre: filterGenre,
        mood: filterMood,
        search: searchText || undefined,
        include_unavailable: true,
      })
      if (res?.tracks) setTracks(res.tracks)
    } catch (e) {
      message.error('加载 BGM 库失败')
    } finally {
      setLoading(false)
    }
  }

  const loadGenres = async () => {
    const res = await listBGMGenres()
    if (res?.genres) setGenres(res.genres)
  }

  const loadMoods = async () => {
    const res = await listBGMMoods()
    if (res?.moods) setMoods(res.moods)
  }

  const handlePlay = (track: any) => {
    if (!track.available) {
      message.warning('该内置示例曲目文件尚未放置，仅展示元数据')
      return
    }
    const url = getBGMFileUrl(track.id)
    if (playingId === track.id) {
      audioRef.current?.pause()
      setPlayingId(null)
      return
    }
    if (audioRef.current) {
      audioRef.current.src = url
      audioRef.current.play().catch(() => message.error('播放失败'))
      setPlayingId(track.id)
    }
  }

  const handleFavorite = async (track: any, e: React.MouseEvent) => {
    e.stopPropagation()
    const res = await toggleBGMFavorite(track.id)
    if (res?.success) {
      setTracks(prev => prev.map(t => t.id === track.id ? { ...t, is_favorite: res.is_favorite } : t))
    }
  }

  const handleDelete = async (track: any, e: React.MouseEvent) => {
    e.stopPropagation()
    if (track.is_builtin) {
      message.warning('内置曲目不可删除')
      return
    }
    try {
      await deleteBGMTrack(track.id)
      message.success('已删除')
      loadLibrary()
    } catch (e) {
      message.error('删除失败')
    }
  }

  const handleMix = async () => {
    if (!videoPath) { message.warning('请输入视频路径'); return }
    if (!selectedTrack) { message.warning('请选择 BGM 曲目'); return }

    setMixing(true)
    try {
      const res = await mixBGM({
        video_path: videoPath,
        bgm_track_id: selectedTrack.id,
        bgm_volume: bgmVolume,
        original_volume: originalVolume,
        fade_in: fadeIn,
        fade_out: fadeOut,
        loop: loopBGM,
      })
      if (res?.task_id) {
        message.success(`混音任务已提交：${selectedTrack.name}`)
        // 加入任务列表
        setMixTasks(prev => [{ ...res, status: 'pending', bgm_name: selectedTrack.name }, ...prev])
        // 开始轮询
        startPolling(res.task_id)
      }
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setMixing(false)
    }
  }

  const startPolling = (taskId: string) => {
    if (pollingRef.current) clearInterval(pollingRef.current)
    pollingRef.current = setInterval(async () => {
      const res = await getBGMMixTask(taskId)
      setMixTasks(prev => prev.map(t => t.task_id === taskId ? { ...t, ...res } : t))
      if (['completed', 'failed'].includes(res?.status)) {
        clearInterval(pollingRef.current!)
        if (res.status === 'completed') {
          message.success(`混音完成：${res.result?.output_path}`)
        } else {
          message.error(`混音失败：${res.message}`)
        }
      }
    }, 2000)
  }

  const handleUpload = async (values: any) => {
    const file = values.file?.file?.originFileObj
    if (!file) { message.warning('请选择音频文件'); return }
    setUploading(true)
    try {
      const res = await uploadBGM(file, {
        name: values.name,
        artist: values.artist,
        genre: values.genre || 'other',
        mood: values.mood || 'neutral',
        bpm: values.bpm || 0,
      })
      if (res?.success) {
        message.success(`"${values.name}" 上传成功`)
        setUploadModal(false)
        uploadForm.resetFields()
        loadLibrary()
      }
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Title level={4} style={{ color: '#fff', marginBottom: 24 }}>
        <CustomerServiceOutlined style={{ marginRight: 8, color: '#f59e0b' }} />
        BGM 配乐
      </Title>

      {/* 隐藏的 audio 标签 */}
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} />

      <Tabs
        defaultActiveKey="library"
        style={{ color: '#ccc' }}
        items={[
          {
            key: 'library',
            label: '🎵 BGM 库',
            children: (
              <>
                {/* 过滤栏 */}
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col xs={24} sm={8}>
                    <Input.Search
                      placeholder="搜索曲名/艺术家..."
                      value={searchText}
                      onChange={e => setSearchText(e.target.value)}
                      onSearch={loadLibrary}
                      style={{ background: '#22223a' }}
                    />
                  </Col>
                  <Col xs={12} sm={6}>
                    <Select
                      allowClear placeholder="风格" value={filterGenre}
                      onChange={setFilterGenre} style={{ width: '100%' }}
                    >
                      {genres.map(g => (
                        <Option key={g} value={g}>
                          {GENRE_ICONS[g] || '🎵'} {g}
                        </Option>
                      ))}
                    </Select>
                  </Col>
                  <Col xs={12} sm={6}>
                    <Select
                      allowClear placeholder="情绪" value={filterMood}
                      onChange={setFilterMood} style={{ width: '100%' }}
                    >
                      {moods.map(m => <Option key={m} value={m}>{m}</Option>)}
                    </Select>
                  </Col>
                  <Col xs={24} sm={4}>
                    <Button
                      icon={<PlusOutlined />} block
                      onClick={() => setUploadModal(true)}
                      style={{ background: '#f59e0b', border: 'none', color: '#000' }}
                    >
                      上传 BGM
                    </Button>
                  </Col>
                </Row>

                {/* 曲目网格 */}
                <Spin spinning={loading}>
                  {tracks.length === 0 ? (
                    <Empty description="暂无曲目" style={{ color: THEME.textSecondary, marginTop: 60 }} />
                  ) : (
                    <Row gutter={[16, 16]}>
                      {tracks.map(track => (
                        <Col xs={24} sm={12} md={8} lg={6} key={track.id}>
                          <Card
                            hoverable
                            onClick={() => setSelectedTrack(track)}
                            style={{
                              background: selectedTrack?.id === track.id ? '#1e1e4a' : '#1a1a2e',
                              border: `2px solid ${selectedTrack?.id === track.id ? '#f59e0b' : '#333'}`,
                              cursor: 'pointer',
                            }}
                            styles={{ body: { padding: 16 } }}
                          >
                            {/* 顶部：风格标签 + 收藏 */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                              <Tag
                                color={GENRE_COLORS[track.genre] || '#666'}
                                style={{ fontSize: 11 }}
                              >
                                {GENRE_ICONS[track.genre] || '🎵'} {track.genre}
                              </Tag>
                              <Space size={4}>
                                <Tooltip title={track.is_favorite ? '取消收藏' : '收藏'}>
                                  <Button
                                    size="small" type="text"
                                    icon={track.is_favorite ? <HeartFilled style={{ color: '#ef4444' }} /> : <HeartOutlined />}
                                    onClick={e => handleFavorite(track, e)}
                                  />
                                </Tooltip>
                                {!track.is_builtin && (
                                  <Button
                                    size="small" type="text" danger
                                    icon={<DeleteOutlined />}
                                    onClick={e => handleDelete(track, e)}
                                  />
                                )}
                              </Space>
                            </div>

                            {/* 曲目信息 */}
                            <Text strong style={{ color: '#fff', display: 'block', marginBottom: 2 }}>
                              {track.name}
                            </Text>
                            <Text style={{ color: THEME.textSecondary, fontSize: 12, display: 'block', marginBottom: 8 }}>
                              {track.artist} · {Math.round(track.duration)}s
                              {track.bpm > 0 && ` · ${track.bpm} BPM`}
                            </Text>

                            {/* 情绪标签 */}
                            {track.mood && (
                              <Tag style={{ fontSize: 10, marginBottom: 8 }}>{track.mood}</Tag>
                            )}

                            {/* 播放按钮 */}
                            <Button
                              size="small" block
                              icon={playingId === track.id ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                              onClick={e => { e.stopPropagation(); handlePlay(track) }}
                              disabled={!track.available}
                              style={{
                                background: playingId === track.id ? '#ef4444' : '#f59e0b',
                                border: 'none',
                                color: '#000',
                                fontWeight: 600,
                              }}
                            >
                              {!track.available ? '文件缺失' : playingId === track.id ? '暂停' : '试听'}
                            </Button>
                          </Card>
                        </Col>
                      ))}
                    </Row>
                  )}
                </Spin>
              </>
            ),
          },
          {
            key: 'mix',
            label: '🎚️ 混音',
            children: (
              <Row gutter={[20, 20]}>
                {/* 左：混音参数 */}
                <Col xs={24} lg={12}>
                  <Card
                    title={<span style={{ color: '#fff' }}>🎚️ 混音设置</span>}
                    style={{ background: '#1a1a2e', border: `1px solid ${THEME.border}` }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }} size={16}>
                      <div>
                        <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>视频文件路径</Text>
                        <Input
                          placeholder="D:/videos/my_video.mp4"
                          value={videoPath}
                          onChange={e => setVideoPath(e.target.value)}
                          style={{ background: '#22223a', borderColor: THEME.border, color: '#fff' }}
                        />
                      </div>

                      <div>
                        <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>
                          已选 BGM：
                          {selectedTrack
                            ? <Tag color={GENRE_COLORS[selectedTrack.genre]}>{selectedTrack.name}</Tag>
                            : <Tag color="default">未选择（去 BGM 库选择）</Tag>}
                        </Text>
                      </div>

                      <div>
                        <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>
                          BGM 音量：{Math.round(bgmVolume * 100)}%
                        </Text>
                        <Slider
                          min={0} max={1} step={0.05}
                          value={bgmVolume} onChange={setBgmVolume}
                          trackStyle={{ background: '#f59e0b' }}
                        />
                      </div>

                      <div>
                        <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>
                          原音量：{Math.round(originalVolume * 100)}%
                        </Text>
                        <Slider
                          min={0} max={1} step={0.05}
                          value={originalVolume} onChange={setOriginalVolume}
                          trackStyle={{ background: '#6366f1' }}
                        />
                      </div>

                      <Row gutter={12}>
                        <Col span={12}>
                          <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>淡入（秒）</Text>
                          <InputNumber min={0} max={10} value={fadeIn} onChange={v => setFadeIn(v || 0)} style={{ width: '100%' }} />
                        </Col>
                        <Col span={12}>
                          <Text style={{ color: '#aaa', display: 'block', marginBottom: 4 }}>淡出（秒）</Text>
                          <InputNumber min={0} max={10} value={fadeOut} onChange={v => setFadeOut(v || 0)} style={{ width: '100%' }} />
                        </Col>
                      </Row>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Switch checked={loopBGM} onChange={setLoopBGM} />
                        <Text style={{ color: '#aaa' }}>BGM 循环（短于视频时自动循环）</Text>
                      </div>

                      <Button
                        type="primary" size="large" block
                        icon={<SoundOutlined />}
                        loading={mixing}
                        onClick={handleMix}
                        disabled={!selectedTrack || !videoPath}
                        style={{ background: '#f59e0b', border: 'none', color: '#000', height: 44, fontWeight: 600 }}
                      >
                        开始混音
                      </Button>
                    </Space>
                  </Card>
                </Col>

                {/* 右：混音任务列表 */}
                <Col xs={24} lg={12}>
                  <Card
                    title={<span style={{ color: '#fff' }}>📋 混音任务</span>}
                    style={{ background: '#1a1a2e', border: `1px solid ${THEME.border}` }}
                  >
                    {mixTasks.length === 0 ? (
                      <Empty description="暂无混音任务" style={{ color: THEME.textSecondary }} />
                    ) : (
                      <Space direction="vertical" style={{ width: '100%' }} size={12}>
                        {mixTasks.map(task => (
                          <div
                            key={task.task_id}
                            style={{
                              background: '#22223a',
                              borderRadius: 8,
                              padding: 14,
                              border: `1px solid ${THEME.border}`,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                              <Text strong style={{ color: '#fff' }}>{task.bgm_name}</Text>
                              <Badge
                                status={STATUS_MAP[task.status]?.color as any || 'default'}
                                text={<span style={{ color: '#aaa' }}>{STATUS_MAP[task.status]?.label}</span>}
                              />
                            </div>
                            <Text style={{ color: THEME.textSecondary, fontSize: 12, display: 'block', marginBottom: 6 }}>
                              {task.message}
                            </Text>
                            {task.status === 'running' && (
                              <Progress percent={Math.round((task.progress || 0) * 100)} size="small" />
                            )}
                            {task.status === 'completed' && task.result?.output_path && (
                              <Text style={{ color: '#4ade80', fontSize: 12 }}>
                                ✅ 输出：{task.result.output_path}
                              </Text>
                            )}
                          </div>
                        ))}
                      </Space>
                    )}
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      {/* 上传 BGM Modal */}
      <Modal
        open={uploadModal}
        title="上传自定义 BGM"
        onCancel={() => setUploadModal(false)}
        footer={null}
      >
        <Form form={uploadForm} layout="vertical" onFinish={handleUpload}>
          <Form.Item name="file" label="音频文件" rules={[{ required: true }]}>
            <Upload accept="audio/*" maxCount={1} beforeUpload={() => false}>
              <Button icon={<UploadOutlined />}>选择文件（MP3/WAV/FLAC）</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="name" label="曲目名称" rules={[{ required: true }]}>
            <Input placeholder="My BGM Track" />
          </Form.Item>
          <Form.Item name="artist" label="艺术家">
            <Input placeholder="未知" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="genre" label="风格">
                <Select placeholder="选择风格">
                  {['upbeat', 'calm', 'epic', 'ambient', 'cinematic', 'jazz', 'other'].map(g => (
                    <Option key={g} value={g}>{GENRE_ICONS[g]} {g}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="mood" label="情绪">
                <Select placeholder="选择情绪">
                  {['happy', 'sad', 'energetic', 'relaxed', 'intense', 'neutral'].map(m => (
                    <Option key={m} value={m}>{m}</Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="bpm" label="BPM（节拍速度）">
            <InputNumber min={0} max={300} placeholder="0" style={{ width: '100%' }} />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={uploading}
            style={{ background: '#f59e0b', border: 'none', color: '#000' }}>
            上传
          </Button>
        </Form>
      </Modal>
    </div>
  )
}
