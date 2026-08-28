import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ArrowUpOutlined,
  BookOutlined,
  DeleteOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  HomeOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { browseReaderLibrary, deleteReaderItem } from '../../api'
import type { ReaderLibraryItem, ReaderLibraryResponse } from '../../api'
import { formatFileSize } from '../../utils/format'

const { Text } = Typography

interface LocalDocumentPickerProps {
  open: boolean
  onCancel: () => void
  onSelectFile: (filePath: string, rootPath?: string) => void
  onSelectFiles: (filePaths: string[], title?: string, rootPath?: string) => void
  onRootChange?: (rootPath: string) => void
}

function formatTime(value: number) {
  if (!value) return '-'
  return new Date(value * 1000).toLocaleString('zh-CN')
}

export default function LocalDocumentPicker({
  open,
  onCancel,
  onSelectFile,
  onSelectFiles,
  onRootChange,
}: LocalDocumentPickerProps) {
  const [rootPath, setRootPath] = useState('')
  const [rootInput, setRootInput] = useState('')
  const [directory, setDirectory] = useState('')
  const [data, setData] = useState<ReaderLibraryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [deletingPath, setDeletingPath] = useState('')
  const [keyword, setKeyword] = useState('')

  const load = async (target = directory, nextRoot = rootPath) => {
    setLoading(true)
    try {
      const res = await browseReaderLibrary(target, nextRoot)
      setData(res)
      setRootPath(res.root_path || '')
      setRootInput(res.root_path || '')
      setDirectory(res.current_relative_path || '')
      onRootChange?.(res.root_path || '')
    } catch (e: any) {
      message.error(e?.message || '读取本地目录失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      load('')
      setKeyword('')
    }
  }, [open])

  const readableFiles = useMemo(() => {
    return (data?.items || []).filter(item => !item.is_dir && item.readable)
  }, [data?.items])

  const visibleItems = useMemo(() => {
    const value = keyword.trim().toLowerCase()
    const items = data?.items || []
    if (!value) return items
    return items.filter(item => item.name.toLowerCase().includes(value))
  }, [data?.items, keyword])

  const enterDirectory = (item: ReaderLibraryItem) => {
    if (!item.is_dir) return
    load(item.relative_path)
  }

  const applyRootPath = () => {
    const nextRoot = rootInput.trim()
    setRootPath(nextRoot)
    setDirectory('')
    setData(null)
    load('', nextRoot)
  }

  const resetRootPath = () => {
    setRootPath('')
    setRootInput('')
    setDirectory('')
    load('', '')
  }

  const openCurrentFolder = () => {
    const files = readableFiles.map(item => item.path)
    if (!files.length) {
      message.warning('当前文件夹没有可阅读文件')
      return
    }
    onSelectFiles(files, data?.current_relative_path || '本地文件夹', rootPath)
  }

  const openFolderAsCollection = async (item: ReaderLibraryItem) => {
    if (!item.is_dir) return
    setLoading(true)
    try {
      const res = await browseReaderLibrary(item.relative_path, rootPath)
      const files = res.items.filter(child => !child.is_dir && child.readable).map(child => child.path)
      if (!files.length) {
        message.warning('该文件夹没有可阅读文件')
        return
      }
      onSelectFiles(files, item.name, rootPath)
    } catch (e: any) {
      message.error(e?.message || '读取本地目录失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (item: ReaderLibraryItem) => {
    setDeletingPath(item.path)
    try {
      const res = await deleteReaderItem(item.path, rootPath, item.is_dir)
      const detail = item.is_dir
        ? `已删除 ${res.deleted_files} 个文件，释放 ${formatFileSize(res.freed_size)}`
        : `已释放 ${formatFileSize(res.freed_size)}`
      message.success(detail)
      await load()
    } catch (e: any) {
      message.error(e?.message || '删除失败')
    } finally {
      setDeletingPath('')
    }
  }

  return (
    <Modal
      title={
        <Space>
          <FolderOpenOutlined />
          本地文件管理
        </Space>
      }
      open={open}
      onCancel={onCancel}
      footer={null}
      width={760}
      destroyOnHidden
    >
      <div className="document-picker">
        <div className="document-picker-root">
          <Input
            value={rootInput}
            onChange={e => setRootInput(e.target.value)}
            onPressEnter={applyRootPath}
            placeholder="输入本机目录路径，留空使用设置里的下载目录"
          />
          <Button type="primary" onClick={applyRootPath} loading={loading}>
            切换目录
          </Button>
          <Tooltip title="回到设置中的下载目录">
            <Button icon={<HomeOutlined />} onClick={resetRootPath} />
          </Tooltip>
        </div>
        <div className="document-picker-toolbar">
          <Space wrap>
            <Button
              icon={<ArrowUpOutlined />}
              disabled={!data?.current_relative_path}
              onClick={() => load(data?.parent_relative_path || '')}
            >
              上级
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>
              刷新
            </Button>
            <Button type="primary" icon={<BookOutlined />} disabled={!readableFiles.length} onClick={openCurrentFolder}>
              打开当前文件夹
            </Button>
          </Space>
          <Input.Search
            allowClear
            placeholder="筛选文件名"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            style={{ width: 220 }}
          />
        </div>

        <div className="document-picker-path">
          <Text type="secondary">下载根目录：</Text>
          <Text code>{data?.root_path || '-'}</Text>
        </div>
        <div className="document-picker-path">
          <Text type="secondary">当前目录：</Text>
          <Text>{data?.current_relative_path || '根目录'}</Text>
          {readableFiles.length > 0 && <Tag color="green">{readableFiles.length} 个可读文件</Tag>}
        </div>

        <List
          className="document-picker-list"
          loading={loading}
          dataSource={visibleItems}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可阅读文件或文件夹" />,
          }}
          renderItem={(item) => (
            <List.Item
              className="document-picker-item"
              actions={item.is_dir ? [
                <Button key="enter" size="small" onClick={() => enterDirectory(item)}>
                  进入
                </Button>,
                <Tooltip key="folder" title="打开该目录下的可读文件，不递归子目录">
                  <Button size="small" icon={<BookOutlined />} onClick={() => openFolderAsCollection(item)}>
                    作为合集
                  </Button>
                </Tooltip>,
                <Popconfirm
                  key="delete"
                  title={`删除文件夹「${item.name}」？`}
                  description="会删除该文件夹及内部所有文件，无法在应用内恢复。"
                  okText="删除文件夹"
                  cancelText="取消"
                  okButtonProps={{ danger: true, loading: deletingPath === item.path }}
                  onConfirm={() => handleDelete(item)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} loading={deletingPath === item.path}>
                    删除
                  </Button>
                </Popconfirm>,
              ] : [
                <Button key="read" size="small" type="primary" onClick={() => onSelectFile(item.path, rootPath)}>
                  阅读
                </Button>,
                <Popconfirm
                  key="delete"
                  title={`删除文件「${item.name}」？`}
                  description="只删除当前文件，不会自动清理同目录图片资源。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true, loading: deletingPath === item.path }}
                  onConfirm={() => handleDelete(item)}
                >
                  <Button size="small" danger icon={<DeleteOutlined />} loading={deletingPath === item.path}>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                avatar={item.is_dir ? <FolderOpenOutlined className="document-picker-icon" /> : <FileTextOutlined className="document-picker-icon" />}
                title={
                  <button
                    type="button"
                    className="document-picker-name"
                    onClick={() => item.is_dir ? enterDirectory(item) : onSelectFile(item.path, rootPath)}
                  >
                    {item.name}
                  </button>
                }
                description={
                  <Space size={8} wrap>
                    <Tag color={item.is_dir ? 'blue' : 'default'}>{item.is_dir ? '文件夹' : item.format.toUpperCase()}</Tag>
                    {!item.is_dir && <Text type="secondary">{formatFileSize(item.file_size)}</Text>}
                    <Text type="secondary">{formatTime(item.modified_at)}</Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </div>
    </Modal>
  )
}
