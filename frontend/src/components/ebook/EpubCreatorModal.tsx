/**
 * EPUB 电子书公共组件
 * 可供素材库、下载页等处嵌入调用
 */
import { useState } from 'react'
import {
  Modal, Form, Input, Button, message, Space, Typography, Alert,
} from 'antd'
import { BookOutlined, FolderOpenOutlined, FileImageOutlined } from '@ant-design/icons'
import { generateEbook, type EbookGenerateResult } from '../../api'

const { Text } = Typography

interface EpubCreatorModalProps {
  open: boolean
  onClose: () => void
  defaultFolder?: string
  defaultTitle?: string
}

export default function EpubCreatorModal({
  open, onClose, defaultFolder = '', defaultTitle = '',
}: EpubCreatorModalProps) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<EbookGenerateResult | null>(null)

  const handleGenerate = async (values: {
    title: string
    folder_path: string
    author: string
    cover_path: string
  }) => {
    setLoading(true)
    setResult(null)
    try {
      const res = await generateEbook(values)
      if (res.status === 'failed') {
        message.error(res.error || '生成失败')
        setResult(res)
      } else {
        message.success(`EPUB 生成完成：${res.chapter_count} 个章节`)
        setResult(res)

        // 自动下载
        if (res.task_id) {
          window.open(`/api/v1/ebook/download/${res.task_id}`, '_blank')
        }
      }
    } catch (e: any) {
      message.error(e?.message || '生成失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={
        <Space>
          <BookOutlined style={{ color: '#07C160' }} />
          <span>生成 EPUB 电子书</span>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnHidden
    >
      <Form
        layout="vertical"
        onFinish={handleGenerate}
        initialValues={{
          title: defaultTitle || '我的电子书',
          folder_path: defaultFolder,
          author: 'YLCraft',
          cover_path: '',
        }}
      >
        <Form.Item
          label={<Space><FolderOpenOutlined />文章文件夹</Space>}
          name="folder_path"
          rules={[{ required: true, message: '请输入或粘贴文件夹路径' }]}
          extra="包含 .md / .html 文件的文件夹路径"
        >
          <Input placeholder="如 /data/wechat_mp/articles" />
        </Form.Item>

        <Form.Item
          label="书名"
          name="title"
          rules={[{ required: true }]}
        >
          <Input placeholder="电子书标题" />
        </Form.Item>

        <Form.Item
          label="作者"
          name="author"
        >
          <Input placeholder="作者名" />
        </Form.Item>

        <Form.Item
          label={<Space><FileImageOutlined />封面图片（可选）</Space>}
          name="cover_path"
          extra="本地图片文件路径"
        >
          <Input placeholder="/path/to/cover.jpg" />
        </Form.Item>

        <Button
          type="primary"
          htmlType="submit"
          loading={loading}
          icon={<BookOutlined />}
          block
          size="large"
        >
          开始生成
        </Button>
      </Form>

      {result && (
        <div style={{ marginTop: 16 }}>
          {result.status === 'done' && (
            <Alert
              type="success"
              message="生成成功"
              description={
                <div>
                  <Text>章节数：{result.chapter_count}</Text>
                  {result.file_size > 0 && (
                    <Text style={{ marginLeft: 12 }}>
                      大小：{(result.file_size / 1024 / 1024).toFixed(1)} MB
                    </Text>
                  )}
                  {result.file_path && (
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }} code>
                        {result.file_path}
                      </Text>
                    </div>
                  )}
                </div>
              }
            />
          )}
          {result.status === 'failed' && (
            <Alert type="error" message="生成失败" description={result.error} />
          )}
        </div>
      )}
    </Modal>
  )
}
