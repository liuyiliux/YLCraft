/**
 * 书源管理页面
 * 支持导入/导出/启用/禁用 阅读App格式的书源
 */

import React, { useState, useEffect } from 'react'
import {
  Card, Button, Table, Tag, Space, Upload, message, Popconfirm,
  Switch, Typography, Divider, Alert
} from 'antd'
import { UploadOutlined, DownloadOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { getBookSources, importBookSources, toggleBookSource, deleteBookSource, exportBookSources } from '../../api/bookSource'

const { Title, Text, Paragraph } = Typography

interface BookSource {
  id: string
  book_source_name: string
  book_source_url: string
  book_source_type: number
  enabled: boolean
  book_source_group?: string
  enabled_by_user: boolean
}

const BookSourcePage: React.FC = () => {
  const [sources, setSources] = useState<BookSource[]>([])
  const [loading, setLoading] = useState(false)

  const fetchSources = async () => {
    setLoading(true)
    try {
      const data = await getBookSources(false)
      setSources(data)
    } catch (err: any) {
      message.error(`加载书源失败: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSources()
  }, [])

  const handleImport = async (file: File) => {
    try {
      const result = await importBookSources(file)
      if (result.success) {
        message.success(`导入成功！新增 ${result.added} 个，更新 ${result.updated} 个，共 ${result.total} 个书源`)
        fetchSources()
      } else {
        message.error(`导入失败: ${result.error}`)
      }
    } catch (err: any) {
      message.error(`导入失败: ${err.message}`)
    }
    return false // 阻止自动上传
  }

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await toggleBookSource(id, enabled)
      message.success(enabled ? '已启用' : '已禁用')
      fetchSources()
    } catch (err: any) {
      message.error(`操作失败: ${err.message}`)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteBookSource(id)
      message.success('删除成功')
      fetchSources()
    } catch (err: any) {
      message.error(`删除失败: ${err.message}`)
    }
  }

  const handleExport = () => {
    exportBookSources()
  }

  const uploadProps: UploadProps = {
    accept: '.json',
    showUploadList: false,
    beforeUpload: handleImport,
  }

  const columns = [
    {
      title: '书源名称',
      dataIndex: 'book_source_name',
      key: 'book_source_name',
      width: 200,
    },
    {
      title: '书源URL',
      dataIndex: 'book_source_url',
      key: 'book_source_url',
      width: 200,
      render: (url: string) => <Text copyable>{url}</Text>,
    },
    {
      title: '分组',
      dataIndex: 'book_source_group',
      key: 'book_source_group',
      width: 100,
      render: (group: string) => group ? <Tag>{group}</Tag> : '-',
    },
    {
      title: '类型',
      dataIndex: 'book_source_type',
      key: 'book_source_type',
      width: 80,
      render: (type: number) => {
        const map = { 0: '文本', 1: '音频', 2: '图片' }
        return map[type as keyof typeof map] || '未知'
      },
    },
    {
      title: '状态',
      key: 'enabled_by_user',
      width: 100,
      render: (_: any, record: BookSource) => (
        <Switch
          checked={record.enabled_by_user}
          onChange={(checked) => handleToggle(record.id, checked)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: BookSource) => (
        <Popconfirm
          title="确定删除此书源？"
          onConfirm={() => handleDelete(record.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button type="link" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>书源管理</Title>
      <Paragraph>
        支持导入<a href="https://github.com/fects/legado" target="_blank" rel="noreferrer">阅读App（Legado）</a>格式的书源文件（.json），
        导入后即可使用对应书源搜索和下载小说。
      </Paragraph>

      <Alert
        type="info"
        showIcon
        message="书源格式说明"
        description={
          <div>
            <p>书源文件通常为 <code>*.json</code> 格式，包含搜索、目录、正文解析规则。</p>
            <p>可从以下途径获取书源：</p>
            <ul>
              <li><a href="https://github.com/fects/legado/app/src/main/assets/bookSource" target="_blank" rel="noreferrer">阅读App 官方书源仓库</a></li>
              <li><a href="https://legado.cn/" target="_blank" rel="noreferrer">阅读App 官网</a></li>
            </ul>
          </div>
        }
        style={{ marginBottom: 16 }}
      />

      <Divider />

      <Space style={{ marginBottom: 16 }}>
        <Upload {...uploadProps}>
          <Button type="primary" icon={<UploadOutlined />}>导入书源JSON</Button>
        </Upload>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>导出书源</Button>
        <Button onClick={fetchSources} loading={loading}>刷新</Button>
      </Space>

      <Card>
        <Table
          dataSource={sources}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20 }}
          scroll={{ x: 800 }}
        />
      </Card>

      <Divider />

      <Title level={4}>使用说明</Title>
      <Paragraph>
        1. 点击「导入书源JSON」按钮，选择书源文件（支持多选或单个）<br/>
        2. 导入后书源会自动启用，可在表格中禁用不需要的书源<br/>
        3. 前往「小说搜索」页面，即可在所有制用书源中搜索小说<br/>
        4. 可导出当前书源配置，备份或分享给其他用户
      </Paragraph>
    </div>
  )
}

export default BookSourcePage
