/**
 * 书源管理页面
 * 支持导入/导出/启用/禁用 阅读App格式的书源
 */

import React, { useState, useEffect } from 'react'
import {
  Card, Button, Table, Tag, Space, Upload, message, Popconfirm,
  Switch, Typography, Divider, Alert, Modal, Form, Input, Select, Descriptions
} from 'antd'
import { UploadOutlined, DownloadOutlined, DeleteOutlined, BugOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import {
  getBookSources,
  importBookSources,
  toggleBookSource,
  deleteBookSource,
  exportBookSources,
  batchToggleBookSources,
  batchDeleteBookSources,
  testBookSource,
} from '../../api/bookSource'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

  interface BookSource {
    id: string
    book_source_name: string
    book_source_url: string
    book_source_type: number
    enabled: boolean
    book_source_group?: string
    enabled_by_user: boolean
    is_js_source: boolean
  }

const BookSourcePage: React.FC = () => {
  const [sources, setSources] = useState<BookSource[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [pagination, setPagination] = useState({ pageSize: 20, current: 1 })
  const [testForm] = Form.useForm()
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [testSource, setTestSource] = useState<BookSource | null>(null)
  const [testResult, setTestResult] = useState<any>(null)

  const handleTableChange = (newPagination: any) => {
    setPagination({
      pageSize: newPagination.pageSize,
      current: newPagination.current,
    })
  }

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
      } else {
        const failedMsg = result.failed > 0 ? `，失败 ${result.failed} 个` : ''
        message.error(`导入部分失败${failedMsg}: ${result.error}`)
      }
      fetchSources()
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

  const handleBatchEnable = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择书源')
      return
    }
    try {
      const result = await batchToggleBookSources(selectedRowKeys as string[], true)
      if (result.failed > 0) {
        message.warning(`已启用 ${result.updated} 个，失败 ${result.failed} 个`)
      } else {
        message.success(`已启用 ${result.updated} 个书源`)
      }
      setSelectedRowKeys([])
      fetchSources()
    } catch (err: any) {
      message.error(`批量启用失败: ${err.message}`)
    }
  }

  const handleBatchDisable = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择书源')
      return
    }
    try {
      const result = await batchToggleBookSources(selectedRowKeys as string[], false)
      if (result.failed > 0) {
        message.warning(`已禁用 ${result.updated} 个，失败 ${result.failed} 个`)
      } else {
        message.success(`已禁用 ${result.updated} 个书源`)
      }
      setSelectedRowKeys([])
      fetchSources()
    } catch (err: any) {
      message.error(`批量禁用失败: ${err.message}`)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先选择书源')
      return
    }
    try {
      const result = await batchDeleteBookSources(selectedRowKeys as string[])
      if (result.failed > 0) {
        message.warning(`已删除 ${result.deleted} 个，失败 ${result.failed} 个`)
      } else {
        message.success(`已删除 ${result.deleted} 个书源`)
      }
      setSelectedRowKeys([])
      fetchSources()
    } catch (err: any) {
      message.error(`批量删除失败: ${err.message}`)
    }
  }

  const handleExport = () => {
    exportBookSources()
  }

  const openTestModal = (source: BookSource) => {
    setTestSource(source)
    setTestResult(null)
    testForm.setFieldsValue({
      url: source.book_source_url,
      keyword: '',
      rule_type: 'search',
      show_raw: true,
    })
    setTestModalOpen(true)
  }

  const handleRunTest = async () => {
    const values = await testForm.validateFields()
    if (!testSource) return
    if (!values.keyword?.trim() && !values.url?.trim()) {
      message.warning('请输入书名/关键词，或填写完整测试 URL')
      return
    }
    setTestLoading(true)
    setTestResult(null)
    try {
      const result = await testBookSource(testSource.id, values)
      if (!result.success) {
        message.error(result.detail || '书源测试失败')
      }
      setTestResult(result)
    } catch (err: any) {
      message.error(`书源测试失败: ${err.message}`)
    } finally {
      setTestLoading(false)
    }
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
      title: '兼容性',
      key: 'is_js_source',
      width: 90,
      render: (_: any, record: BookSource) =>
        record.is_js_source
          ? <Tag color="error">JS源</Tag>
          : <Tag color="success">可用</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: any, record: BookSource) => (
        <Space size={4}>
          <Button type="link" icon={<BugOutlined />} onClick={() => openTestModal(record)}>
            测试
          </Button>
          <Popconfirm
            title="确定删除此书源？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
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

      <Space style={{ marginBottom: 16 }} wrap>
        <Upload {...uploadProps}>
          <Button type="primary" icon={<UploadOutlined />}>导入书源JSON</Button>
        </Upload>
        <Button icon={<DownloadOutlined />} onClick={handleExport}>导出书源</Button>
        <Button onClick={fetchSources} loading={loading}>刷新</Button>
        <Button type="primary" onClick={handleBatchEnable} disabled={selectedRowKeys.length === 0}>批量启用</Button>
        <Button danger onClick={handleBatchDisable} disabled={selectedRowKeys.length === 0}>批量禁用</Button>
        <Button type="primary" danger onClick={handleBatchDelete} disabled={selectedRowKeys.length === 0}>批量删除</Button>
      </Space>

      <Card>
        <Table
          dataSource={sources}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total, range) => `${range[0]}-${range[1]} / 共 ${total} 条`,
            onChange: (page, pageSize) => {
              setPagination({ current: page, pageSize: pageSize || 20 })
            },
          }}
          scroll={{ x: 900 }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
        />
      </Card>

      <Divider />

      <Title level={4}>使用说明</Title>
      <Paragraph>
        1. 点击「导入书源JSON」按钮，选择书源文件（支持多选或单个）<br/>
        2. 导入后书源会自动启用，可在表格中禁用不需要的书源<br/>
        3. 前往「小说搜索」页面，即可在所有启用书源中搜索小说<br/>
        4. 可导出当前书源配置，备份或分享给其他用户
      </Paragraph>

      <Modal
        open={testModalOpen}
        title={testSource ? `测试书源：${testSource.book_source_name}` : '测试书源'}
        width={920}
        onCancel={() => setTestModalOpen(false)}
        onOk={handleRunTest}
        okText="开始测试"
        cancelText="关闭"
        confirmLoading={testLoading}
      >
        <Form form={testForm} layout="vertical" initialValues={{ rule_type: 'search', show_raw: true }}>
          <Form.Item name="keyword" label="书名 / 搜索关键词">
            <Input placeholder="例如：斗破苍穹" allowClear />
          </Form.Item>
          <Form.Item
            name="url"
            label="测试 URL（可选）"
            rules={[
              {
                validator: (_, value) => {
                  if (!value || /^https?:\/\//i.test(value)) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('请输入完整的 http:// 或 https:// 地址'))
                },
              },
            ]}
            extra="搜索测试会优先使用书名按书源模板生成 URL；目录/正文测试可直接粘贴目标页面 URL。"
          >
            <Input placeholder="https://example.com/search?q=小说名" />
          </Form.Item>
          <Space align="start" wrap>
            <Form.Item name="rule_type" label="解析类型" style={{ minWidth: 180 }}>
              <Select
                allowClear
                placeholder="自动识别"
                options={[
                  { label: '搜索结果', value: 'search' },
                  { label: '目录列表', value: 'toc' },
                  { label: '章节正文', value: 'content' },
                ]}
              />
            </Form.Item>
            <Form.Item name="show_raw" label="返回原始 HTML" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
          </Space>
        </Form>

        {testResult?.detail && (
          <Alert type="error" showIcon message="测试失败" description={testResult.detail} style={{ marginBottom: 16 }} />
        )}

        {testResult?.data && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="最终 URL" span={2}>
                <Text copyable>{testResult.data.url}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态码">{testResult.data.status_code}</Descriptions.Item>
              <Descriptions.Item label="耗时">{testResult.data.response_time_ms} ms</Descriptions.Item>
              <Descriptions.Item label="解析类型">{testResult.data.debug_info?.rule_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="命中元素">{testResult.data.debug_info?.matched_elements ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="使用 Cookie">{testResult.data.debug_info?.cookie_used ? '是' : '否'}</Descriptions.Item>
              <Descriptions.Item label="解析耗时">{testResult.data.debug_info?.parse_time_ms ?? '-'} ms</Descriptions.Item>
            </Descriptions>

            <div>
              <Text strong>解析结果</Text>
              <TextArea
                readOnly
                value={JSON.stringify(testResult.data.parsed_result, null, 2)}
                rows={8}
                style={{ marginTop: 8, fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <Text strong>调试信息</Text>
              <TextArea
                readOnly
                value={JSON.stringify(testResult.data.debug_info, null, 2)}
                rows={6}
                style={{ marginTop: 8, fontFamily: 'monospace' }}
              />
            </div>

            {testResult.data.raw_html && (
              <div>
                <Text strong>原始 HTML 预览</Text>
                {testResult.data.raw_html_truncated && <Tag color="warning" style={{ marginLeft: 8 }}>已截断</Tag>}
                <TextArea
                  readOnly
                  value={testResult.data.raw_html}
                  rows={10}
                  style={{ marginTop: 8, fontFamily: 'monospace' }}
                />
              </div>
            )}
          </Space>
        )}
      </Modal>
      </div>
  )
}

export default BookSourcePage
