import { useState, useEffect, useRef } from 'react'
import {
  Alert, Card, Input, Button, Typography, Tag, Spin, message, Space, Divider, Progress, Table, Upload, Modal,
} from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CloudDownloadOutlined, AudioOutlined, PlayCircleOutlined, LinkOutlined, DeleteOutlined, FolderOpenOutlined,
  PictureOutlined, DownloadOutlined, SaveOutlined, InboxOutlined, PauseCircleOutlined, ReloadOutlined
} from '@ant-design/icons'
import {
  addTorrentMagnet,
  deleteTorrentTask,
  getTorrentEngineInfo,
  getTorrentFiles,
  getTorrentFileStreamUrl,
  getTorrentTask,
  importTorrentAssets,
  listPlatformConnections,
  listTorrentTasks,
  openFolder,
  parseDownloadUrl,
  pauseTorrentTask,
  refreshTorrentMetadata,
  resumeTorrentTask,
  selectTorrentFiles,
  uploadTorrentFile,
  createDownloadTask,
  getDownloadTask,
  wechatMpDownloadSingle,
} from '../../api'
import type { DownloadParseResponse, VideoQuality } from '../../types/api'
import { useTheme } from '../../constants/theme'
import { normalizeUrl } from '../../utils/url'
import { formatFileSize } from '../../utils/format'

const { Title, Text, Paragraph } = Typography

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: 'B站', douyin: '抖音', kuaishou: '快手',
  xiaohongshu: '小红书', weibo: '微博', youtube: 'YouTube', tiktok: 'TikTok',
  twitter: 'Twitter/X', telegram: 'Telegram', wechat_mp: '微信公众号',
  unknown: '未知平台',
}

const QUALITY_COLORS: Record<string, string> = {
  '4K': '#f59e0b', '2K': '#8b5cf6', '1080P': '#10b981',
  '720P': '#3b82f6', '480P': '#6366f1', '360P': '#8b8ba8', '240P': '#8b8ba8',
}

const PREVIEW_READY_POLL_ATTEMPTS = 20
const PREVIEW_READY_POLL_INTERVAL_MS = 3000
const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

interface TorrentTask {
  id: string
  name: string
  status: string
  progress: number
  torrent_hash: string
  download_speed: number
  upload_speed: number
  downloaded_bytes: number
  total_size: number
  selected_files: number[]
  asset_ids: string[]
  error_message?: string
}

interface TorrentFile {
  index: number
  name: string
  size: number
  progress: number
  priority: number
  is_video: boolean
}

interface TorrentEngineInfo {
  engine: string
  download_dir: string
  metadata_cache_dir?: string
  max_active: number
  listen_interfaces?: string
  metadata_cache_providers?: number
  requires_external_app: boolean
  libtorrent_available?: boolean
  hint?: string
}

interface PreviewWaitState {
  taskId: string
  fileIndex: number
  fileName: string
  status: 'starting' | 'waiting' | 'stalled'
  checkedCount: number
}

function TorrentDownloadPanel() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [magnet, setMagnet] = useState('')
  const [tasks, setTasks] = useState<TorrentTask[]>([])
  const [activeTask, setActiveTask] = useState<TorrentTask | null>(null)
  const [files, setFiles] = useState<TorrentFile[]>([])
  const [selectedFiles, setSelectedFiles] = useState<number[]>([])
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [adding, setAdding] = useState(false)
  const [filesLoading, setFilesLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState('')
  const [engineInfo, setEngineInfo] = useState<TorrentEngineInfo | null>(null)
  const [preview, setPreview] = useState<{ taskId: string; fileIndex: number; title: string; url: string; progress: number } | null>(null)
  const [previewWait, setPreviewWait] = useState<PreviewWaitState | null>(null)
  const activeTaskRef = useRef<TorrentTask | null>(null)
  const filesRef = useRef<TorrentFile[]>([])

  useEffect(() => {
    activeTaskRef.current = activeTask
  }, [activeTask])

  useEffect(() => {
    filesRef.current = files
  }, [files])

  const refreshTasks = async () => {
    setLoadingTasks(true)
    try {
      const res: any = await listTorrentTasks()
      const nextTasks = (res?.data || []) as TorrentTask[]
      setTasks(nextTasks)
      const currentActive = activeTaskRef.current
      if (currentActive) {
        const nextActive = nextTasks.find(item => item.id === currentActive.id) || null
        setActiveTask(nextActive)
        if (nextActive && (filesRef.current.length === 0 || nextActive.status === 'metadata')) {
          try {
            const filesRes: any = await getTorrentFiles(nextActive.id)
            const nextFiles = (filesRes?.data || []) as TorrentFile[]
            setFiles(nextFiles)
            if (nextFiles.length && !selectedFiles.length) {
              setSelectedFiles(nextFiles.filter(item => item.is_video).map(item => item.index))
            }
          } catch {
            // Keep the current table while metadata is still unavailable.
          }
        }
      }
    } catch (e: any) {
      message.error(e?.message || '获取种子任务失败')
    } finally {
      setLoadingTasks(false)
    }
  }

  const loadEngineInfo = async () => {
    try {
      const res: any = await getTorrentEngineInfo()
      setEngineInfo((res?.data || null) as TorrentEngineInfo | null)
    } catch {
      setEngineInfo(null)
    }
  }

  const loadFiles = async (task: TorrentTask) => {
    setActiveTask(task)
    setFilesLoading(true)
    try {
      const res: any = await getTorrentFiles(task.id)
      const nextFiles = (res?.data || []) as TorrentFile[]
      setFiles(nextFiles)
      setSelectedFiles(task.selected_files?.length ? task.selected_files : nextFiles.filter(item => item.is_video).map(item => item.index))
    } catch (e: any) {
      message.error(e?.message || '获取种子文件列表失败')
      setFiles([])
    } finally {
      setFilesLoading(false)
    }
  }

  useEffect(() => {
    loadEngineInfo()
    refreshTasks()
    const timer = window.setInterval(refreshTasks, 5000)
    return () => window.clearInterval(timer)
  }, [])

  const addMagnet = async () => {
    const value = magnet.trim()
    if (!value) {
      message.warning('请输入磁力链接')
      return
    }
    setAdding(true)
    try {
      const res: any = await addTorrentMagnet(value, true)
      const task = res?.data as TorrentTask
      message.success('磁力任务已添加')
      setMagnet('')
      await refreshTasks()
      if (task?.id) {
        const detail: any = await getTorrentTask(task.id)
        await loadFiles(detail?.data || task)
      }
    } catch (e: any) {
      message.error(e?.message || '添加磁力任务失败')
    } finally {
      setAdding(false)
    }
  }

  const runTaskAction = async (key: string, action: () => Promise<any>, successText: string) => {
    setActionLoading(key)
    try {
      const res: any = await action()
      message.success(successText)
      await refreshTasks()
      if (res?.data?.id) await loadFiles(res.data)
      return res
    } catch (e: any) {
      message.error(e?.message || '操作失败')
      return null
    } finally {
      setActionLoading('')
    }
  }

  const startSelectedFiles = async () => {
    if (!activeTask) return
    if (!selectedFiles.length) {
      message.warning('请选择至少一个文件')
      return
    }
    await runTaskAction(
      `select-${activeTask.id}`,
      () => selectTorrentFiles(activeTask.id, selectedFiles, true),
      '已开始下载选中文件',
    )
  }

  const importAssets = async (task: TorrentTask) => {
    const res = await runTaskAction(`import-${task.id}`, () => importTorrentAssets(task.id), '已导入素材库')
    const assetId = res?.data?.[0]?.id
    if (assetId) navigate(`/player/assets/${assetId}`)
  }

  const retryMetadata = async (task: TorrentTask) => {
    await runTaskAction(
      `metadata-${task.id}`,
      () => refreshTorrentMetadata(task.id),
      '已重新公告，正在获取种子元数据',
    )
  }

  const openPreview = (item: TorrentFile) => {
    if (!activeTask) return
    if (!item.is_video) {
      message.warning('只能在线播放视频文件')
      return
    }
    setPreview({
      taskId: activeTask.id,
      fileIndex: item.index,
      title: item.name,
      url: getTorrentFileStreamUrl(activeTask.id, item.index),
      progress: Math.round((item.progress || 0) * 100),
    })
  }

  const waitForPreviewProgress = async (taskId: string, fileIndex: number, fileName: string) => {
    for (let attempt = 0; attempt < PREVIEW_READY_POLL_ATTEMPTS; attempt += 1) {
      if (attempt > 0) await sleep(PREVIEW_READY_POLL_INTERVAL_MS)
      const res: any = await getTorrentFiles(taskId)
      const nextFiles = (res?.data || []) as TorrentFile[]
      setFiles(nextFiles)
      const target = nextFiles.find(file => file.index === fileIndex) || null
      if (target && (target.progress || 0) > 0) return target
      setPreviewWait({ taskId, fileIndex, fileName: target?.name || fileName, status: 'waiting', checkedCount: attempt + 1 })
    }
    return null
  }

  const startStreamingPreview = async (item: TorrentFile) => {
    if (!activeTask) return
    if (!item.is_video) {
      message.warning('只能在线播放视频文件')
      return
    }
    if ((item.progress || 0) > 0) {
      openPreview(item)
      return
    }

    const taskId = activeTask.id
    const loadingKey = `stream-${taskId}-${item.index}`
    const nextSelection = Array.from(new Set([...selectedFiles, item.index]))
    setActionLoading(loadingKey)
    setPreviewWait({ taskId, fileIndex: item.index, fileName: item.name, status: 'starting', checkedCount: 0 })
    try {
      setSelectedFiles(nextSelection)
      await selectTorrentFiles(taskId, nextSelection, true)
      message.success('已开始下载当前视频，正在等待可预览片段')
      setPreviewWait({ taskId, fileIndex: item.index, fileName: item.name, status: 'waiting', checkedCount: 0 })
      const readyFile = await waitForPreviewProgress(taskId, item.index, item.name)
      await refreshTasks()
      if (readyFile && (readyFile.progress || 0) > 0) {
        setPreviewWait(null)
        setPreview({
          taskId,
          fileIndex: readyFile.index,
          title: readyFile.name,
          url: getTorrentFileStreamUrl(taskId, readyFile.index),
          progress: Math.round((readyFile.progress || 0) * 100),
        })
        return
      }
      setPreviewWait({
        taskId,
        fileIndex: item.index,
        fileName: item.name,
        status: 'stalled',
        checkedCount: PREVIEW_READY_POLL_ATTEMPTS,
      })
      message.warning('已开始下载，但本地片段还没准备好；稍后再点边下边播即可继续尝试')
    } catch (e: any) {
      setPreviewWait(null)
      message.error(e?.message || '启动边下边播失败')
    } finally {
      setActionLoading('')
    }
  }

  const startPreviewFile = async () => {
    if (!preview) return
    const nextSelection = activeTask?.id === preview.taskId
      ? Array.from(new Set([...selectedFiles, preview.fileIndex]))
      : [preview.fileIndex]
    await runTaskAction(
      `preview-${preview.taskId}-${preview.fileIndex}`,
      () => selectTorrentFiles(preview.taskId, nextSelection, true),
      '已开始下载当前视频',
    )
    if (activeTask?.id === preview.taskId) setSelectedFiles(nextSelection)
  }

  const engineName = engineInfo?.engine || 'qbittorrent'
  const engineMessage = engineInfo?.requires_external_app
    ? '当前使用本机 qBittorrent 引擎，需要 qBittorrent Web UI 可用'
    : engineName === 'libtorrent'
      ? '当前使用本地 libtorrent 引擎，无需安装桌面下载软件'
      : `当前使用本地 ${engineName} 引擎`
  const engineDescription = (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text style={{ color: THEME.textSecondary }}>
        {engineInfo?.requires_external_app
          ? '添加任务后会交给本机 qBittorrent 获取元数据和下载文件；选择视频文件并拿到本地片段后可直接在线播放，下载完成后也可导入素材库。'
          : '添加任务后由后端本地下载引擎获取元数据和下载文件；选择视频文件并拿到本地片段后可直接在线播放，下载完成后也可导入素材库。'}
      </Text>
      <Text style={{ color: THEME.textSecondary }}>
        YLCraft 是开源本地模式，不内置云端离线、秒传或 CDN 缓存；这里只缓存种子元数据和本机已下载文件。若任务长期 0 B/s，通常表示本机还没从 peer、tracker 或 DHT 拿到数据；迅雷、夸克能播放往往是因为它们有自己的云端资源网络。
      </Text>
      {engineInfo && (
        <Space size={6} wrap>
          <Tag color={engineInfo.requires_external_app ? 'gold' : 'blue'}>{engineInfo.engine}</Tag>
          <Tag color={engineInfo.libtorrent_available ? 'green' : 'default'}>
            libtorrent {engineInfo.libtorrent_available ? '已安装' : '未安装'}
          </Tag>
          <Text style={{ color: THEME.textSecondary, fontSize: 12, wordBreak: 'break-all' }}>
            下载目录：{engineInfo.download_dir}
          </Text>
          {engineInfo.metadata_cache_dir && (
            <Text style={{ color: THEME.textSecondary, fontSize: 12, wordBreak: 'break-all' }}>
              元数据缓存：{engineInfo.metadata_cache_dir}
            </Text>
          )}
          <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
            最大任务：{engineInfo.max_active}
          </Text>
          {engineInfo.listen_interfaces && (
            <Text style={{ color: THEME.textSecondary, fontSize: 12, wordBreak: 'break-all' }}>
              监听：{engineInfo.listen_interfaces}
            </Text>
          )}
          {typeof engineInfo.metadata_cache_providers === 'number' && (
            <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
              元数据缓存源：{engineInfo.metadata_cache_providers}
            </Text>
          )}
        </Space>
      )}
    </Space>
  )

  const taskColumns = [
    {
      title: '任务',
      dataIndex: 'name',
      render: (_: string, item: TorrentTask) => (
        <div style={{ minWidth: 0 }}>
          <Text style={{ color: THEME.textPrimary }} ellipsis>{item.name || item.torrent_hash || item.id}</Text>
          {item.error_message && (
            <div>
              <Text type={item.status === 'metadata' ? 'secondary' : 'danger'} style={{ fontSize: 12 }}>
                {item.error_message}
              </Text>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (status: string) => <Tag color={status === 'done' ? 'green' : status === 'failed' ? 'red' : status === 'paused' ? 'gold' : 'blue'}>{status}</Tag>,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 180,
      render: (progress: number, item: TorrentTask) => (
        <div>
          <Progress percent={progress || 0} size="small" showInfo={false} />
          <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
            {formatFileSize(item.downloaded_bytes || 0)} / {formatFileSize(item.total_size || 0)}
          </Text>
        </div>
      ),
    },
    {
      title: '速度',
      width: 150,
      render: (_: unknown, item: TorrentTask) => (
        <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
          ↓ {formatFileSize(item.download_speed || 0)}/s · ↑ {formatFileSize(item.upload_speed || 0)}/s
        </Text>
      ),
    },
    {
      title: '操作',
      width: 260,
      render: (_: unknown, item: TorrentTask) => (
        <Space wrap>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => loadFiles(item)}>文件</Button>
          {item.status === 'metadata' && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={actionLoading === `metadata-${item.id}`}
              onClick={() => retryMetadata(item)}
            >
              重试元数据
            </Button>
          )}
          {item.status === 'paused' ? (
            <Button size="small" icon={<ReloadOutlined />} loading={actionLoading === `resume-${item.id}`} onClick={() => runTaskAction(`resume-${item.id}`, () => resumeTorrentTask(item.id), '已继续下载')}>继续</Button>
          ) : (
            <Button size="small" icon={<PauseCircleOutlined />} loading={actionLoading === `pause-${item.id}`} onClick={() => runTaskAction(`pause-${item.id}`, () => pauseTorrentTask(item.id), '已暂停')}>暂停</Button>
          )}
          <Button size="small" icon={<SaveOutlined />} loading={actionLoading === `import-${item.id}`} onClick={() => importAssets(item)}>入库</Button>
          {item.asset_ids?.[0] && <Button size="small" icon={<PlayCircleOutlined />} onClick={() => navigate(`/player/assets/${item.asset_ids[0]}`)}>播放</Button>}
          <Button size="small" danger icon={<DeleteOutlined />} loading={actionLoading === `delete-${item.id}`} onClick={() => runTaskAction(`delete-${item.id}`, () => deleteTorrentTask(item.id), '已删除任务')}>删除</Button>
        </Space>
      ),
    },
  ]

  const fileColumns = [
    {
      title: '文件',
      dataIndex: 'name',
      render: (name: string, item: TorrentFile) => (
        <Space>
          {item.is_video && <Tag color="blue">视频</Tag>}
          {item.is_video && item.progress >= 1 && <Tag color="green">已完成</Tag>}
          {item.is_video && item.progress > 0 && item.progress < 1 && <Tag color="cyan">可预览</Tag>}
          {item.is_video && item.progress <= 0 && <Tag color="default">未下载</Tag>}
          <Text style={{ color: THEME.textPrimary }}>{name}</Text>
        </Space>
      ),
    },
    { title: '大小', dataIndex: 'size', width: 120, render: (size: number) => formatFileSize(size || 0) },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 160,
      render: (progress: number) => <Progress percent={Math.round((progress || 0) * 100)} size="small" />,
    },
    {
      title: '操作',
      width: 130,
      render: (_: unknown, item: TorrentFile) => {
        const isWaitingForThis = !!activeTask
          && previewWait?.taskId === activeTask.id
          && previewWait.fileIndex === item.index
          && previewWait.status !== 'stalled'
        const isStalledForThis = !!activeTask
          && previewWait?.taskId === activeTask.id
          && previewWait.fileIndex === item.index
          && previewWait.status === 'stalled'
        return (
          <Button
            size="small"
            icon={<PlayCircleOutlined />}
            loading={activeTask ? actionLoading === `stream-${activeTask.id}-${item.index}` : false}
            disabled={!item.is_video}
            onClick={() => startStreamingPreview(item)}
          >
            {isWaitingForThis ? '等待片段' : (item.progress || 0) > 0 ? '播放' : isStalledForThis ? '重试边播' : '边下边播'}
          </Button>
        )
      },
    },
  ]

  const currentPreviewWaitFile = previewWait && activeTask?.id === previewWait.taskId
    ? files.find(item => item.index === previewWait.fileIndex)
    : null

  return (
    <>
      <Card
        title={<Space><InboxOutlined style={{ color: THEME.primary }} /><Text style={{ color: THEME.textPrimary }}>磁力 / 种子下载</Text></Space>}
        style={{ background: THEME.bgCard, marginBottom: 24, border: `1px solid ${THEME.border}` }}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type={engineInfo?.requires_external_app ? 'warning' : 'info'}
            showIcon
            message={engineMessage}
            description={engineDescription}
          />
          <Space.Compact style={{ width: '100%' }}>
            <Input
              size="large"
              placeholder="magnet:?xt=urn:btih:..."
              value={magnet}
              onChange={event => setMagnet(event.target.value)}
              onPressEnter={addMagnet}
              style={{ background: THEME.bgInput, color: THEME.textPrimary }}
            />
            <Button type="primary" size="large" icon={<CloudDownloadOutlined />} loading={adding} onClick={addMagnet}>
              添加
            </Button>
          </Space.Compact>
          <Upload
            accept=".torrent"
            showUploadList={false}
            beforeUpload={async file => {
              setAdding(true)
              try {
                const res: any = await uploadTorrentFile(file, true)
                message.success('种子任务已添加')
                await refreshTasks()
                if (res?.data) await loadFiles(res.data)
              } catch (e: any) {
                message.error(e?.message || '上传种子失败')
              } finally {
                setAdding(false)
              }
              return false
            }}
          >
            <Button icon={<InboxOutlined />} loading={adding}>上传 .torrent</Button>
          </Upload>
          <Table
            rowKey="id"
            size="small"
            loading={loadingTasks}
            dataSource={tasks}
            columns={taskColumns}
            pagination={false}
            scroll={{ x: 900 }}
          />
          {activeTask && (
            <Card
              size="small"
              title={<Text style={{ color: THEME.textPrimary }}>文件选择：{activeTask.name || activeTask.id}</Text>}
              style={{ background: THEME.bgInput, border: `1px solid ${THEME.border}` }}
              extra={
                <Button type="primary" size="small" loading={actionLoading === `select-${activeTask.id}`} onClick={startSelectedFiles}>
                  下载选中文件
                </Button>
              }
            >
              {!filesLoading && files.length === 0 && (
                <Alert
                  type={activeTask.status === 'metadata' ? 'info' : 'warning'}
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={activeTask.status === 'metadata' ? '正在获取种子元数据' : '还没有可选择的文件'}
                  action={activeTask.status === 'metadata' ? (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      loading={actionLoading === `metadata-${activeTask.id}`}
                      onClick={() => retryMetadata(activeTask)}
                    >
                      重试元数据
                    </Button>
                  ) : undefined}
                  description={
                    activeTask.status === 'metadata'
                      ? activeTask.error_message || 'magnet 需要先从 DHT/Tracker/Peer 拉到文件列表。文件列表出现后，视频行右侧会显示“播放”按钮；选中文件并开始下载后，进度大于 0 就可以预览。'
                      : '点击任务右侧“文件”刷新列表；如果仍为空，可能是种子元数据暂未获取完成或当前任务没有文件信息。'
                  }
                />
              )}
              {previewWait && activeTask.id === previewWait.taskId && (
                <Alert
                  type={previewWait.status === 'stalled' ? 'warning' : 'info'}
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={
                    previewWait.status === 'stalled'
                      ? '还没有等到可预览片段'
                      : '正在准备边下边播'
                  }
                  description={
                    previewWait.status === 'stalled'
                      ? '任务已经开始下载，但本机还没有拿到可播放片段，当前文件仍是 0%。通常是可用 peer 少、tracker/DHT 未连通，或文件前段尚未下载；YLCraft 不走云端离线/秒传缓存。可以继续等待速度起来，换更健康的种子，或用外部网盘/离线工具对比。'
                      : `已选中「${previewWait.fileName}」并启动本地下载，正在等本机拿到第一个可播放片段；这依赖 peer/tracker/DHT，不会使用云端缓存。已检查 ${previewWait.checkedCount}/${PREVIEW_READY_POLL_ATTEMPTS} 次。`
                  }
                  action={currentPreviewWaitFile ? (
                    <Button
                      size="small"
                      icon={<PlayCircleOutlined />}
                      loading={actionLoading === `stream-${activeTask.id}-${currentPreviewWaitFile.index}`}
                      onClick={() => startStreamingPreview(currentPreviewWaitFile)}
                    >
                      {(currentPreviewWaitFile.progress || 0) > 0 ? '打开播放' : '重试边播'}
                    </Button>
                  ) : undefined}
                />
              )}
              <Table
                rowKey="index"
                size="small"
                loading={filesLoading}
                dataSource={files}
                columns={fileColumns}
                pagination={false}
                rowSelection={{
                  selectedRowKeys: selectedFiles,
                  onChange: keys => setSelectedFiles(keys.map(Number)),
                }}
                scroll={{ x: 780, y: 260 }}
              />
            </Card>
          )}
        </Space>
      </Card>

      <Modal
        open={!!preview}
        title={preview?.title || '在线播放'}
        footer={preview ? [
          <Button key="close" onClick={() => setPreview(null)}>关闭</Button>,
          preview.progress < 100 && (
            <Button
              key="download"
              type="primary"
              loading={actionLoading === `preview-${preview.taskId}-${preview.fileIndex}`}
              onClick={startPreviewFile}
            >
              继续下载此文件
            </Button>
          ),
        ] : null}
        width={860}
        destroyOnClose
        onCancel={() => setPreview(null)}
      >
        {preview && (
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            {preview.progress < 100 && (
              <Alert
                type="info"
                showIcon
                message={`当前文件已下载约 ${preview.progress}%`}
                description="边下边播取决于文件格式和已下载片段；MP4 若索引在文件尾部，可能需要下载更多后才能播放。"
              />
            )}
            <video
              key={preview.url}
              src={preview.url}
              controls
              autoPlay
              style={{ width: '100%', maxHeight: '70vh', background: '#000', borderRadius: 6 }}
            />
          </Space>
        )}
      </Modal>
    </>
  )
}

export default function DownloadPage() {
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()
  const [url, setUrl] = useState('')
  const [wechatConnId, setWechatConnId] = useState<string>('')
  const [wechatDownloading, setWechatDownloading] = useState(false)
  const [wechatDownloadedPath, setWechatDownloadedPath] = useState('')

  // 加载微信连接
  useEffect(() => {
    listPlatformConnections().then((res: any) => {
      const wechatConns = (res.connections || []).filter(
        (c: any) => c.platform === 'wechat_mp' && c.status === 'active'
      )
      if (wechatConns.length > 0) {
        setWechatConnId(wechatConns[0].id)
      }
    }).catch(() => {})
  }, [])

  // 从 URL 参数自动填充
  useEffect(() => {
    const urlParam = searchParams.get('url')
    if (urlParam && !url) {
      setUrl(normalizeUrl(urlParam))
    }
  }, [searchParams, url])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DownloadParseResponse | null>(null)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [dlProgress, setDlProgress] = useState(0)
  const [dlError, setDlError] = useState('')
  const [savedFilePath, setSavedFilePath] = useState('')

  // 智能检测 URL 并给出提示
  const getUrlHint = (inputUrl: string) => {
    if (!inputUrl) return null
    const url = inputUrl.toLowerCase()

    if (url.includes('web.telegram.org') && !url.includes('t.me/')) {
      return {
        type: 'warning',
        text: '⚠️ 检测到 Telegram Web 链接，请使用右键消息→「复制链接」获取 https://t.me/ 格式的链接'
      }
    }

    if ((url.includes('twitter.com') || url.includes('x.com')) && url.includes('/photo/')) {
      return {
        type: 'info',
        text: 'ℹ️ 检测到这是 Twitter/X 图片链接，我们会尝试解析图片（目前只支持视频）'
      }
    }

    if (url.includes('twitter.com') || url.includes('x.com')) {
      return {
        type: 'info',
        text: 'ℹ️ Twitter/X 链接可能需要登录才能解析，请确认内容是公开的'
      }
    }

    if (url.includes('mp.weixin.qq.com')) {
      return {
        type: 'info',
        text: 'ℹ️ 检测到微信公众号文章链接，将尝试解析文章标题、正文和图片。如需批量下载，请前往「内容搜索」→「微信公众号」'
      }
    }

    return null
  }

  const urlHint = getUrlHint(url)

  const handleParse = async () => {
    if (!url.trim()) { message.warning('请输入视频链接'); return }
    const trimmed = url.trim()
    if (!/^https?:\/\/.+/.test(trimmed)) { message.warning('请输入有效的 URL 链接'); return }
    setLoading(true); setError(''); setResult(null)
    try {
      const data = await parseDownloadUrl(trimmed)
      if (data.success) { setResult(data); message.success('解析成功') }
      else { setError(data.error || '解析失败'); message.error(data.error || '解析失败') }
    } catch (e: any) {
      const errMsg = e?.response?.data?.detail || '解析请求失败，请检查后端服务'
      setError(errMsg); message.error(errMsg)
    } finally { setLoading(false) }
  }

  const openSavedFolder = async (filePath: string) => {
    if (!filePath) return
    try { await openFolder(filePath) } catch { message.error('无法打开文件夹') }
  }

  const handleDownload = async (quality: VideoQuality | null, isAudio = false) => {
    if (!result) return
    setDownloading(true); setDlProgress(0); setDlError(''); setSavedFilePath('')
    try {
      const downloadUrl = result.video_url || result.page_url || url
      const { task_id } = await createDownloadTask(downloadUrl, quality?.quality, result.title, result.page_url, result.asset_id)
      let pollCount = 0
      const poll = async (): Promise<void> => {
        const res = await getDownloadTask(task_id)
        const task = res
        setDlProgress(Math.min(task.progress || pollCount * 5, 100))
        if (task.status === 'DONE') {
          setSavedFilePath(task.result?.file_path || ''); setDlProgress(100); message.success('下载完成')
          setTimeout(() => setDownloading(false), 3000); return
        }
        if (task.status === 'FAILED') throw new Error(task.error || '下载失败')
        pollCount++
        if (pollCount > 300) throw new Error('下载超时，请稍后重试')
        await new Promise(r => setTimeout(r, 2000)); return poll()
      }
      await poll()
    } catch (e: any) { setDlError(e?.message || String(e)); setDownloading(false) }
  }

  const platformLabel = result ? (PLATFORM_LABELS[result.platform] || result.platform) : ''

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3} style={{ color: THEME.textPrimary, marginBottom: 24 }}>
        <CloudDownloadOutlined style={{ color: THEME.primary, marginRight: 8 }} />
        内容去水印解析
        <Text style={{ color: THEME.textSecondary, fontSize: 14, marginLeft: 12 }}>
          支持视频和图片 · 1000+ 平台（抖音/B站/Twitter 等）
        </Text>
      </Title>

      {/* Input Card */}
      <Card style={{ background: THEME.bgCard, marginBottom: 24, border: `1px solid ${THEME.border}` }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            size="large"
            placeholder="粘贴视频或图片链接（支持 1000+ 平台，包括抖音/B站/Twitter 等）..."
            value={url} onChange={e => setUrl(normalizeUrl(e.target.value))} onPressEnter={handleParse}
            style={{ background: THEME.bgInput, color: THEME.textPrimary }}
            prefix={<LinkOutlined style={{ color: THEME.textSecondary }} />}
            suffix={url && (
              <DeleteOutlined style={{ color: THEME.textSecondary, cursor: 'pointer' }}
                onClick={() => { setUrl(''); setResult(null); setError('') }}
              />
            )}
          />

          {/* URL 智能提示 */}
          {urlHint && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 6,
              backgroundColor: urlHint.type === 'warning' ? 'rgba(245,158,11,0.1)' : 'rgba(59,130,246,0.1)',
              border: `1px solid ${urlHint.type === 'warning' ? '#f59e0b' : '#3b82f6'}33`,
              color: urlHint.type === 'warning' ? '#f59e0b' : '#3b82f6',
              fontSize: 13
            }}>
              {urlHint.text}
            </div>
          )}

          <Button type="primary" size="large" icon={<CloudDownloadOutlined />}
            onClick={handleParse} loading={loading} style={{ height: 44, minWidth: 140 }}>
            立即解析
          </Button>
        </Space>
        {/* Platform quick tags */}
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(PLATFORM_LABELS).filter(([k]) => k !== 'unknown').map(([key, label]) => (
            <Tag key={key} style={{
              cursor: 'pointer',
              border: url.includes(key) ? `1px solid ${THEME.primary}` : `1px solid ${THEME.borderLight}`,
              color: url.includes(key) ? THEME.primary : THEME.textSecondary,
              background: url.includes(key) ? THEME.primaryAlpha(0.08) : 'transparent',
            }} onClick={() => setUrl(`https://example.com/${key}`)}>
              {label}
            </Tag>
          ))}
        </div>
      </Card>

      <TorrentDownloadPanel />

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
          <Paragraph style={{ color: THEME.textSecondary, marginTop: 16 }}>解析中，请稍候...</Paragraph>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <Card style={{ background: THEME.bgCard, marginBottom: 16, border: '1px solid rgba(239,68,68,0.3)' }}>
          <Text style={{ color: THEME.error }}>解析失败：{error}</Text>
        </Card>
      )}

      {/* Result */}
      {result && result.success && !loading && (
        <div>
          {/* 内容信息卡（视频/图片） */}
          <Card title={
            <Space>
              {result.images && result.images.length > 0 ? (
                <PictureOutlined style={{ color: '#00bcd4' }} />
              ) : (
                <PlayCircleOutlined style={{ color: THEME.primary }} />
              )}
              <Text style={{ color: result.images && result.images.length > 0 ? '#00bcd4' : THEME.primary }}>
                {result.images && result.images.length > 0 ? '图片信息' : '视频信息'}
              </Text>
              {platformLabel && <Tag color={result.images && result.images.length > 0 ? 'cyan' : 'blue'}>{platformLabel}</Tag>}
            </Space>
          } style={{ 
            background: THEME.bgCard, 
            marginBottom: 16, 
            border: `1px solid ${THEME.border}`
          }}>
            <div style={{ display: 'flex', gap: 20 }}>
              {/* 如果有图片，优先显示图片 */}
              {result.images && result.images.length > 0 ? (
                <div style={{ flexShrink: 0, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {result.images.slice(0, 4).map((img, idx) => (
                    <div key={idx} style={{
                      width: 140, height: 'auto', borderRadius: 8, overflow: 'hidden',
                      background: THEME.bgInput, aspectRatio: '4/3', display: 'flex',
                      alignItems: 'center', justifyContent: 'center'
                    }}>
                      <img
                        src={img}
                        alt={`图片 ${idx + 1}`}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    </div>
                  ))}
                  {result.images.length > 4 && (
                    <div style={{
                      width: 140, aspectRatio: '4/3', borderRadius: 8,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(0,0,0,0.5)', color: 'white'
                    }}>
                      +{result.images.length - 4}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ flexShrink: 0, width: 180, height: 101, borderRadius: 8, overflow: 'hidden', background: THEME.bgInput }}>
                  <img src={result.cover_url?.includes('hdslb.com') || result.cover_url?.includes('xhscdn.com') || result.cover_url?.includes('douyincdn.com')
                    ? `/api/v1/proxy/image?url=${encodeURIComponent(result.cover_url)}`
                    : result.cover_url?.replace('http://', 'https://')
                  } alt="cover" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </div>
              )}
              
              <div style={{ flex: 1, minWidth: 0 }}>
                <Paragraph strong style={{ color: THEME.textPrimary, fontSize: 16, marginBottom: 8 }} ellipsis={{ rows: 2 }}>
                  {result.title || '未知标题'}
                </Paragraph>
                <Space direction="vertical" size={4}>
                  <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>作者：{result.author || '未知'}</Text>
                  {result.duration_str && (
                    <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>时长：{result.duration_str}</Text>
                  )}
                  {(result.resolution || (result.width && result.height)) && (
                    <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>
                      分辨率：{result.resolution || `${result.width}x${result.height}`}
                    </Text>
                  )}
                  {result.images && result.images.length > 0 && (
                    <Text style={{ color: '#00bcd4', fontSize: 13 }}>图片数量：{result.images.length}</Text>
                  )}
                </Space>
                
                {/* 下载按钮 */}
                {result.platform === 'wechat_mp' ? (
                  <div style={{ marginTop: 12 }}>
                    <Button 
                      type="primary" 
                      icon={<DownloadOutlined />} 
                      loading={wechatDownloading}
                      disabled={!wechatConnId}
                      onClick={async () => {
                        if (!wechatConnId) {
                          message.warning('请先在账号中心登录微信公众号')
                          return
                        }
                        setWechatDownloading(true)
                        setWechatDownloadedPath('')
                        try {
                          const res: any = await wechatMpDownloadSingle({
                            conn_id: wechatConnId,
                            article_url: result.page_url || url,
                            article_title: result.title || '',
                            format: 'md',
                          })
                          if (res?.success) {
                            setWechatDownloadedPath(res.file_path || '')
                            message.success(`已下载到 ${res.file_path}`)
                          } else {
                            message.error(res?.error || '下载失败')
                          }
                        } catch (e: any) {
                          message.error(e?.message || '下载失败')
                        } finally {
                          setWechatDownloading(false)
                        }
                      }}
                      size="small"
                      style={{ background: '#07C160', borderColor: '#07C160' }}
                    >
                      下载 Markdown
                    </Button>
                    {!wechatConnId && (
                      <Text style={{ color: '#f59e0b', fontSize: 12, display: 'block', marginTop: 8 }}>
                        ⚠️ 需要先在账号中心登录微信公众号
                      </Text>
                    )}
                    {wechatDownloadedPath && (
                      <Text style={{ color: '#10b981', fontSize: 12, display: 'block', marginTop: 8 }}>
                        ✓ 已保存到：{wechatDownloadedPath}
                      </Text>
                    )}
                  </div>
                ) : result.images && result.images.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <Button type="primary" icon={<DownloadOutlined />} onClick={() => {
                      result.images?.forEach(img => {
                        window.open(img, '_blank')
                      })
                    }} size="small">打开图片</Button>
                    <Button icon={<SaveOutlined />} onClick={() => {
                      // 简单的方式：打开新窗口让用户自己保存
                      result.images?.forEach((img, idx) => {
                        setTimeout(() => window.open(img, '_blank'), idx * 300)
                      })
                    }} size="small" style={{ marginLeft: 8 }}>保存图片</Button>
                  </div>
                ) : (
                  <>
                    {result.video_url && result.video_url !== url && (
                      <div style={{ marginTop: 12 }}>
                        <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => handleDownload(null)} size="small">下载视频</Button>
                        {result.audio_url && (
                          <Button icon={<AudioOutlined />} onClick={() => handleDownload(null, true)} size="small" style={{ marginLeft: 8 }}>下载音频</Button>
                        )}
                      </div>
                    )}
                    {(!result.video_url || result.video_url === url) && (
                      <Text style={{ color: '#f59e0b', fontSize: 12, display: 'block', marginTop: 8 }}>
                        ⚠️ B站等平台链接有时效限制，建议使用专业下载工具（如 yt-dlp）
                      </Text>
                    )}
                  </>
                )}
              </div>
            </div>
          </Card>

          {/* 视频下载（仅在有视频时显示） */}
          {(result.qualities.length > 0 || result.video_url) && !(result.images && result.images.length > 0) && (
            <Card title={
              <Space>
                <CloudDownloadOutlined style={{ color: '#f59e0b' }} />
                <Text style={{ color: '#f59e0b' }}>视频下载</Text>
              </Space>
            } style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              {result.qualities.length > 0 ? (
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {result.qualities.map((q, i) => {
                    const color = QUALITY_COLORS[q.quality] || THEME.primary
                    const displayText = q.resolution && q.quality && q.resolution !== q.quality 
                      ? `${q.resolution} (${q.quality})` 
                      : q.resolution || q.quality
                    return (
                      <Button key={i} type="default" size="large" icon={<CloudDownloadOutlined />}
                        onClick={() => handleDownload(q)} disabled={downloading}
                        style={{ height: 52, padding: '0 24px', border: `1px solid ${color}44`, color, background: downloading ? 'rgba(0,0,0,0.04)' : `${color}11` }}>
                        <div style={{ lineHeight: 1.2 }}>
                          <div style={{ fontSize: 14, fontWeight: 700 }}>{displayText}</div>
                          <div style={{ fontSize: 11, opacity: 0.7 }}>{q.filesize}</div>
                        </div>
                      </Button>
                    )
                  })}
                </div>
              ) : (
                <div>
                  <Paragraph style={{ color: THEME.textSecondary, marginBottom: 16 }}>
                    当前链接为直链格式（{platformLabel || '未知平台'} CDN），建议使用 yt-dlp 等专业工具下载以获得更高画质：
                  </Paragraph>
                  <code style={{ display: 'block', background: THEME.bgInput, padding: '12px 16px', borderRadius: 6, color: '#10b981', fontFamily: 'monospace', fontSize: 13 }}>
                    yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{result.video_url && result.video_url !== url ? result.video_url : url}"
                  </code>
                  {result.video_url && result.video_url !== url && (
                    <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => handleDownload(null)} disabled={downloading} style={{ marginTop: 16 }}>尝试直接下载当前链接</Button>
                  )}
                </div>
              )}

              {result.audio_url && (
                <>
                  <Divider style={{ borderColor: THEME.border }} />
                  <Button icon={<AudioOutlined />} onClick={() => handleDownload(null, true)} size="large" disabled={downloading}
                    style={{ border: '1px solid rgba(168,85,247,0.4)', color: '#a855f7', background: 'rgba(168,85,247,0.08)' }}>
                    <div style={{ lineHeight: 1.2 }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>音频下载</div>
                      <div style={{ fontSize: 11, opacity: 0.7 }}>MP3 / M4A</div>
                    </div>
                  </Button>
                </>
              )}

              {/* Download progress */}
              {downloading && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                    <CloudDownloadOutlined style={{ color: THEME.primary, fontSize: 16 }} />
                    <Text style={{ color: THEME.textPrimary, fontSize: 13 }}>
                      {dlProgress < 50 ? '正在获取视频信息...' : dlProgress < 100 ? '正在下载视频...' : '正在保存文件...'}
                    </Text>
                    <Text style={{ color: THEME.primary, fontSize: 13, marginLeft: 'auto' }}>{dlProgress}%</Text>
                  </div>
                  <Progress percent={dlProgress} size="small" status={dlProgress >= 100 ? 'success' : 'active'}
                    strokeColor={{ '0%': THEME.primary, '100%': '#00ff88' }} showInfo={false} style={{ marginBottom: 0 }} />
                </div>
              )}

              {dlError && !downloading && (
                <Text style={{ color: THEME.error, fontSize: 12, marginTop: 8, display: 'block' }}>下载失败：{dlError}</Text>
              )}

              {/* 保存路径 */}
              {savedFilePath && (
                <div style={{ marginTop: 16, padding: '12px 16px', background: THEME.primaryAlpha(0.08), borderRadius: 8, border: `1px solid ${THEME.primaryAlpha(0.2)}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <FolderOpenOutlined style={{ color: THEME.primary }} />
                    <Text style={{ color: THEME.textPrimary, fontSize: 13, fontWeight: 600 }}>保存路径</Text>
                  </div>
                  <Paragraph style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 8, wordBreak: 'break-all' }}
                    copyable={{ text: savedFilePath }}>{savedFilePath}</Paragraph>
                  <Button size="small" icon={<FolderOpenOutlined />} onClick={() => openSavedFolder(savedFilePath)}
                    style={{ color: THEME.primary, borderColor: THEME.primary }}>打开文件夹</Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
