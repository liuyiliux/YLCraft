/**
 * 书源管理页面
 * 支持导入、导出、启用、禁用，以及书源规则调试。
 */

import React, { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import type { TableProps, UploadProps } from 'antd'
import {
  BugOutlined,
  DeleteOutlined,
  DownloadOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
  SwapOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  batchDeleteBookSources,
  batchToggleBookSources,
  convertBookSourceRules,
  createBookSourceCookie,
  deleteBookSource,
  deleteBookSourceCookie,
  exportBookSources,
  getBookSourceCookies,
  getBookSourceRules,
  getBookSources,
  importBookSources,
  testBookSource,
  toggleBookSource,
  updateBookSourceCookie,
  updateBookSourceRules,
} from '../../api/bookSource'
import type {
  BookSource,
  BookSourceCookie,
  BookSourceRules,
  BookSourceRulesPayload,
} from '../../api/bookSource'
import { useTheme } from '../../constants/theme'

const { Title, Text, Paragraph } = Typography
const { TextArea, Search } = Input

interface LegadoRuleEditor {
  searchUrl: string
  ruleSearch: string
  ruleBookInfo: string
  ruleToc: string
  ruleContent: string
  ruleExplore: string
}

const emptyRuleEditor = (): LegadoRuleEditor => ({
  searchUrl: '',
  ruleSearch: '{}',
  ruleBookInfo: '{}',
  ruleToc: '{}',
  ruleContent: '{}',
  ruleExplore: '{}',
})

const jsonText = (value: unknown) => JSON.stringify(value || {}, null, 2)

const darkInfoAlertStyle: React.CSSProperties = {
  background: '#2b2112',
  borderColor: '#8a6418',
}

const darkInfoAlertTitleStyle: React.CSSProperties = {
  color: '#ffd666',
  fontWeight: 600,
}

const darkInfoAlertDescriptionStyle: React.CSSProperties = {
  color: '#f6e2b3',
}

const darkWarningAlertStyle: React.CSSProperties = {
  background: '#2b2112',
  borderColor: '#8a6418',
}

const darkWarningAlertTitleStyle: React.CSSProperties = {
  color: '#ffd666',
  fontWeight: 600,
}

const darkWarningAlertDescriptionStyle: React.CSSProperties = {
  color: '#f6e2b3',
}

const parseJsonObject = (text: string, label: string): Record<string, any> => {
  const source = (text || '').trim()
  if (!source) return {}
  const parsed = JSON.parse(source)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} 必须是 JSON 对象`)
  }
  return parsed
}

const defaultTestHeadersText = () => jsonText({
  'User-Agent': typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
  Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
  'Accept-Language': 'zh-CN,zh;q=0.9',
  'Cache-Control': 'no-cache',
  Pragma: 'no-cache',
  'Sec-Fetch-Dest': 'document',
  'Sec-Fetch-Mode': 'navigate',
  'Sec-Fetch-Site': 'none',
  'Sec-Fetch-User': '?1',
  'Upgrade-Insecure-Requests': '1',
})

const parseHeadersInput = (text: string): Record<string, string> => {
  const source = (text || '').trim()
  if (!source) return {}
  if (source.startsWith('{')) {
    const parsed = parseJsonObject(source, '请求头')
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([key, value]) => [key, String(value)]),
    )
  }

  const headers: Record<string, string> = {}
  for (const line of source.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    if (/^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+\S+\s+HTTP\/\d(?:\.\d)?$/i.test(trimmed)) {
      continue
    }
    const index = trimmed.indexOf(':')
    if (index <= 0) continue
    const key = trimmed.slice(0, index).trim()
    const value = trimmed.slice(index + 1).trim()
    if (key && value) headers[key] = value
  }
  return headers
}

const BookSourcePage: React.FC = () => {
  const { themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  const [sources, setSources] = useState<BookSource[]>([])
  const [loading, setLoading] = useState(false)
  const [sourceNameKeyword, setSourceNameKeyword] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [pagination, setPagination] = useState({ pageSize: 20, current: 1 })

  const [debugOpen, setDebugOpen] = useState(false)
  const [debugSource, setDebugSource] = useState<BookSource | null>(null)
  const [activeDebugTab, setActiveDebugTab] = useState('test')
  const [testForm] = Form.useForm()
  const fetchMode = Form.useWatch('fetch_mode', testForm) || 'http'
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)

  const [rulesLoading, setRulesLoading] = useState(false)
  const [rulesSaving, setRulesSaving] = useState(false)
  const [convertLoading, setConvertLoading] = useState<'legado' | 'ylcraft' | null>(null)
  const [rulesMeta, setRulesMeta] = useState<BookSourceRules | null>(null)
  const [legadoEditor, setLegadoEditor] = useState<LegadoRuleEditor>(emptyRuleEditor())
  const [ylcraftText, setYlcraftText] = useState('{}')

  const [cookies, setCookies] = useState<BookSourceCookie[]>([])
  const [cookiesLoading, setCookiesLoading] = useState(false)
  const [cookieSaving, setCookieSaving] = useState(false)
  const [editingCookie, setEditingCookie] = useState<BookSourceCookie | null>(null)
  const [cookieForm] = Form.useForm()

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

  const filteredSources = useMemo(() => {
    const keyword = sourceNameKeyword.trim().toLowerCase()
    if (!keyword) return sources
    return sources.filter(source =>
      (source.book_source_name || '').toLowerCase().includes(keyword),
    )
  }, [sources, sourceNameKeyword])

  const applyRules = (data: BookSourceRules) => {
    setRulesMeta(data)
    setLegadoEditor({
      searchUrl: data.legado?.searchUrl || '',
      ruleSearch: jsonText(data.legado?.ruleSearch),
      ruleBookInfo: jsonText(data.legado?.ruleBookInfo),
      ruleToc: jsonText(data.legado?.ruleToc),
      ruleContent: jsonText(data.legado?.ruleContent),
      ruleExplore: jsonText(data.legado?.ruleExplore),
    })
    setYlcraftText(jsonText(data.ylcraft))
  }

  const loadRules = async (source: BookSource) => {
    setRulesLoading(true)
    try {
      const data = await getBookSourceRules(source.id)
      applyRules(data)
    } catch (err: any) {
      message.error(`加载规则失败: ${err.message}`)
    } finally {
      setRulesLoading(false)
    }
  }

  const loadCookies = async (sourceId: string) => {
    setCookiesLoading(true)
    try {
      const data = await getBookSourceCookies(sourceId)
      setCookies(data)
    } catch (err: any) {
      message.error(`加载 Cookie 失败: ${err.message}`)
    } finally {
      setCookiesLoading(false)
    }
  }

  const openDebugModal = (source: BookSource) => {
    setDebugSource(source)
    setDebugOpen(true)
    setActiveDebugTab('test')
    setTestResult(null)
    setRulesMeta(null)
    setLegadoEditor(emptyRuleEditor())
    setYlcraftText('{}')
    setCookies([])
    setEditingCookie(null)
    testForm.setFieldsValue({
      keyword: '',
      url: '',
      page: 1,
      rule_type: 'search',
      rule_format: 'legado',
      fetch_mode: 'http',
      show_raw: true,
      request_headers: defaultTestHeadersText(),
    })
    cookieForm.resetFields()
    loadRules(source)
    loadCookies(source.id)
  }

  const buildLegadoPayload = (): BookSourceRulesPayload => ({
    save_format: 'legado',
    search_url: legadoEditor.searchUrl,
    rule_search: parseJsonObject(legadoEditor.ruleSearch, '搜索规则'),
    rule_book_info: parseJsonObject(legadoEditor.ruleBookInfo, '详情规则'),
    rule_toc: parseJsonObject(legadoEditor.ruleToc, '目录规则'),
    rule_content: parseJsonObject(legadoEditor.ruleContent, '正文规则'),
    rule_explore: parseJsonObject(legadoEditor.ruleExplore, '发现规则'),
  })

  const buildYlcraftPayload = (): BookSourceRulesPayload => ({
    save_format: 'ylcraft',
    search_url: legadoEditor.searchUrl,
    rule_explore: parseJsonObject(legadoEditor.ruleExplore, '发现规则'),
    ylcraft_rule: parseJsonObject(ylcraftText, 'YLCraft 规则'),
  })

  const buildLegadoSourceForConvert = () => ({
    bookSourceName: debugSource?.book_source_name || rulesMeta?.book_source_name || '',
    bookSourceUrl: debugSource?.book_source_url || rulesMeta?.book_source_url || '',
    searchUrl: legadoEditor.searchUrl,
    ruleSearch: parseJsonObject(legadoEditor.ruleSearch, '搜索规则'),
    ruleBookInfo: parseJsonObject(legadoEditor.ruleBookInfo, '详情规则'),
    ruleToc: parseJsonObject(legadoEditor.ruleToc, '目录规则'),
    ruleContent: parseJsonObject(legadoEditor.ruleContent, '正文规则'),
    ruleExplore: parseJsonObject(legadoEditor.ruleExplore, '发现规则'),
  })

  const handleImport = async (file: File) => {
    try {
      const result = await importBookSources(file)
      if (result.success) {
        message.success(`导入成功：新增 ${result.added} 个，更新 ${result.updated} 个，共 ${result.total} 个书源`)
      } else {
        const failedMsg = (result.failed || 0) > 0 ? `，失败 ${result.failed} 个` : ''
        message.error(`导入部分失败${failedMsg}: ${result.error}`)
      }
      fetchSources()
    } catch (err: any) {
      message.error(`导入失败: ${err.message}`)
    }
    return false
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
      message.success(`已启用 ${result.updated} 个书源`)
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
      message.success(`已禁用 ${result.updated} 个书源`)
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
      message.success(`已删除 ${result.deleted} 个书源`)
      setSelectedRowKeys([])
      fetchSources()
    } catch (err: any) {
      message.error(`批量删除失败: ${err.message}`)
    }
  }

  const handleRunTest = async () => {
    const values = await testForm.validateFields()
    if (!debugSource) return
    if (!values.keyword?.trim() && !values.url?.trim()) {
      message.warning('请输入书名关键词，或填写完整测试 URL')
      return
    }

    let rules: BookSourceRulesPayload
    let headers: Record<string, string>
    try {
      rules = values.rule_format === 'ylcraft' ? buildYlcraftPayload() : buildLegadoPayload()
      headers = parseHeadersInput(values.request_headers)
    } catch (err: any) {
      message.error(err.message)
      return
    }

    setTestLoading(true)
    setTestResult(null)
    try {
      const result = await testBookSource(debugSource.id, {
        url: values.url,
        keyword: values.keyword,
        page: values.page,
        rule_type: values.rule_type,
        rule_format: values.rule_format,
        fetch_mode: values.fetch_mode,
        show_raw: values.show_raw,
        headers,
        rules,
      })
      setTestResult(result)
      if (!result.success) {
        message.error(result.detail || '书源测试失败')
      }
    } catch (err: any) {
      message.error(`书源测试失败: ${err.message}`)
    } finally {
      setTestLoading(false)
    }
  }

  const handleSaveLegadoRules = async () => {
    if (!debugSource) return
    let payload: BookSourceRulesPayload
    try {
      payload = buildLegadoPayload()
    } catch (err: any) {
      message.error(err.message)
      return
    }

    setRulesSaving(true)
    try {
      const data = await updateBookSourceRules(debugSource.id, payload)
      applyRules(data)
      message.success('Legado 规则已保存，并已同步生成 YLCraft 规则')
      fetchSources()
    } catch (err: any) {
      message.error(`保存规则失败: ${err.message}`)
    } finally {
      setRulesSaving(false)
    }
  }

  const handleSaveYlcraftRules = async () => {
    if (!debugSource) return
    let payload: BookSourceRulesPayload
    try {
      payload = buildYlcraftPayload()
    } catch (err: any) {
      message.error(err.message)
      return
    }

    setRulesSaving(true)
    try {
      const data = await updateBookSourceRules(debugSource.id, payload)
      applyRules(data)
      message.success('YLCraft 规则已保存，并已同步回写 Legado 规则')
      fetchSources()
    } catch (err: any) {
      message.error(`保存规则失败: ${err.message}`)
    } finally {
      setRulesSaving(false)
    }
  }

  const handleConvertToYlcraft = async () => {
    try {
      setConvertLoading('ylcraft')
      const converted = await convertBookSourceRules('legado_to_ylcraft', buildLegadoSourceForConvert())
      setYlcraftText(jsonText(converted))
      const warnings = converted.conversion_warnings || []
      if (warnings.length > 0) {
        message.warning(`转换完成，有 ${warnings.length} 条提示`)
      } else {
        message.success('已转换为 YLCraft 规则')
      }
    } catch (err: any) {
      message.error(`转换失败: ${err.message}`)
    } finally {
      setConvertLoading(null)
    }
  }

  const handleConvertToLegado = async () => {
    try {
      setConvertLoading('legado')
      const converted = await convertBookSourceRules('ylcraft_to_legado', parseJsonObject(ylcraftText, 'YLCraft 规则'))
      setLegadoEditor(prev => ({
        ...prev,
        searchUrl: converted.searchUrl || '',
        ruleSearch: jsonText(converted.ruleSearch),
        ruleBookInfo: jsonText(converted.ruleBookInfo),
        ruleToc: jsonText(converted.ruleToc),
        ruleContent: jsonText(converted.ruleContent),
      }))
      message.success('已转换为 Legado 规则')
    } catch (err: any) {
      message.error(`转换失败: ${err.message}`)
    } finally {
      setConvertLoading(null)
    }
  }

  const handleCookieSubmit = async () => {
    if (!debugSource) return
    const values = await cookieForm.validateFields()
    const cookieContent = values.cookie_content?.trim()
    if (!editingCookie && !cookieContent) {
      message.warning('新增 Cookie 时必须填写 Cookie 内容')
      return
    }

    const payload: any = {
      domain: values.domain,
      description: values.description || '',
      is_active: values.is_active ?? true,
      expires_at: values.expires_at || null,
    }
    if (cookieContent) payload.cookie_content = cookieContent

    setCookieSaving(true)
    try {
      if (editingCookie) {
        await updateBookSourceCookie(debugSource.id, editingCookie.id, payload)
        message.success('Cookie 已更新')
      } else {
        await createBookSourceCookie(debugSource.id, payload)
        message.success('Cookie 已新增')
      }
      setEditingCookie(null)
      cookieForm.resetFields()
      cookieForm.setFieldsValue({ is_active: true })
      loadCookies(debugSource.id)
    } catch (err: any) {
      message.error(`保存 Cookie 失败: ${err.message}`)
    } finally {
      setCookieSaving(false)
    }
  }

  const handleCookieActiveChange = async (cookie: BookSourceCookie, checked: boolean) => {
    if (!debugSource) return
    try {
      await updateBookSourceCookie(debugSource.id, cookie.id, { is_active: checked })
      loadCookies(debugSource.id)
    } catch (err: any) {
      message.error(`更新 Cookie 失败: ${err.message}`)
    }
  }

  const handleDeleteCookie = async (cookieId: string) => {
    if (!debugSource) return
    try {
      await deleteBookSourceCookie(debugSource.id, cookieId)
      message.success('Cookie 已删除')
      loadCookies(debugSource.id)
    } catch (err: any) {
      message.error(`删除 Cookie 失败: ${err.message}`)
    }
  }

  const startEditCookie = (cookie: BookSourceCookie) => {
    setEditingCookie(cookie)
    cookieForm.setFieldsValue({
      domain: cookie.domain,
      description: cookie.description,
      cookie_content: '',
      expires_at: cookie.expires_at || '',
      is_active: cookie.is_active,
    })
  }

  const uploadProps: UploadProps = {
    accept: '.json',
    showUploadList: false,
    beforeUpload: handleImport,
  }

  const columns: TableProps<BookSource>['columns'] = [
    {
      title: '书源名称',
      dataIndex: 'book_source_name',
      key: 'book_source_name',
      width: 220,
    },
    {
      title: '书源 URL',
      dataIndex: 'book_source_url',
      key: 'book_source_url',
      width: 240,
      render: (url: string) => <Text copyable>{url}</Text>,
    },
    {
      title: '分组',
      dataIndex: 'book_source_group',
      key: 'book_source_group',
      width: 120,
      render: (group: string) => (group ? <Tag>{group}</Tag> : '-'),
    },
    {
      title: '类型',
      dataIndex: 'book_source_type',
      key: 'book_source_type',
      width: 90,
      render: (type: number) => {
        const map = { 0: '文本', 1: '音频', 2: '图片' }
        return map[type as keyof typeof map] || '未知'
      },
    },
    {
      title: '规则',
      key: 'rule_format',
      width: 120,
      render: (_, record) => (
        <Space size={4}>
          <Tag color={record.rule_format === 'ylcraft' ? 'blue' : 'default'}>
            {record.rule_format || 'legado'}
          </Tag>
          {record.rule_version && <Text type="secondary">{record.rule_version}</Text>}
        </Space>
      ),
    },
    {
      title: '状态',
      key: 'enabled_by_user',
      width: 110,
      render: (_, record) => (
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
      width: 100,
      render: (_, record) =>
        record.is_js_source ? <Tag color="error">含 JS</Tag> : <Tag color="success">可用</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space size={4}>
          <Button type="link" icon={<BugOutlined />} onClick={() => openDebugModal(record)}>
            调试
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

  const renderTestResult = () => {
    if (testResult?.detail) {
      return <Alert type="error" showIcon message="测试失败" description={testResult.detail} />
    }
    if (!testResult?.data) return null

    const data = testResult.data
    const diagnostics = data.diagnostics || data.debug_info?.diagnostics || []
    return (
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="请求方式">{data.request_info?.method || '-'}</Descriptions.Item>
          <Descriptions.Item label="状态码">{data.status_code}</Descriptions.Item>
          <Descriptions.Item label="最终 URL" span={2}>
            <Text copyable>{data.url}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="耗时">{data.response_time_ms} ms</Descriptions.Item>
          <Descriptions.Item label="解析耗时">{data.debug_info?.parse_time_ms ?? '-'} ms</Descriptions.Item>
          <Descriptions.Item label="解析类型">{data.debug_info?.rule_type || '-'}</Descriptions.Item>
          <Descriptions.Item label="规则格式">{data.debug_info?.rule_format || '-'}</Descriptions.Item>
          <Descriptions.Item label="请求模式">{data.debug_info?.fetch_mode === 'browser' ? '浏览器渲染' : '普通请求'}</Descriptions.Item>
          <Descriptions.Item label="命中元素">{data.debug_info?.matched_elements ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="使用 Cookie">
            {data.debug_info?.cookie_used ? '是' : '否'}
          </Descriptions.Item>
        </Descriptions>

        {diagnostics.map((item: any, index: number) => (
          <Alert
            key={`${item.type || 'diagnostic'}-${index}`}
            type="warning"
            showIcon
            style={isDark ? darkWarningAlertStyle : undefined}
            message={<span style={isDark ? darkWarningAlertTitleStyle : undefined}>{item.message}</span>}
            description={
              item.suggestion ? (
                <span style={isDark ? darkWarningAlertDescriptionStyle : undefined}>{item.suggestion}</span>
              ) : undefined
            }
          />
        ))}

        {data.request_info && (
          <div>
            <Text strong>请求预览</Text>
            <TextArea
              readOnly
              value={JSON.stringify(data.request_info, null, 2)}
              rows={5}
              style={{ marginTop: 8, fontFamily: 'monospace' }}
            />
          </div>
        )}

        <div>
          <Text strong>解析结果</Text>
          <TextArea
            readOnly
            value={JSON.stringify(data.parsed_result, null, 2)}
            rows={9}
            style={{ marginTop: 8, fontFamily: 'monospace' }}
          />
        </div>

        <div>
          <Text strong>调试信息</Text>
          <TextArea
            readOnly
            value={JSON.stringify(data.debug_info, null, 2)}
            rows={8}
            style={{ marginTop: 8, fontFamily: 'monospace' }}
          />
        </div>

        {data.raw_html && (
          <div>
            <Space>
              <Text strong>原始 HTML 预览</Text>
              {data.raw_html_truncated && <Tag color="warning">已截断</Tag>}
            </Space>
            <TextArea
              readOnly
              value={data.raw_html}
              rows={10}
              style={{ marginTop: 8, fontFamily: 'monospace' }}
            />
          </div>
        )}
      </Space>
    )
  }

  const renderTestTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Alert
        type="info"
        showIcon
        style={isDark ? darkInfoAlertStyle : undefined}
        message={<span style={isDark ? darkInfoAlertTitleStyle : undefined}>测试会使用当前编辑器里的规则</span>}
        description={
          <span style={isDark ? darkInfoAlertDescriptionStyle : undefined}>
            可以先修改 Legado 或 YLCraft 规则，直接运行测试；只有点击保存规则时才会写入书源。
          </span>
        }
      />
      {fetchMode === 'browser' && (
        <Alert
          type="warning"
          showIcon
          style={isDark ? darkWarningAlertStyle : undefined}
          message={<span style={isDark ? darkWarningAlertTitleStyle : undefined}>浏览器渲染会调用 Patchright</span>}
          description={
            <span style={isDark ? darkWarningAlertDescriptionStyle : undefined}>
              适合调试起点这类会返回探测页的网站；后端需要已安装 Patchright，否则测试会返回安装提示。
            </span>
          }
        />
      )}
      <Form form={testForm} layout="vertical" initialValues={{ rule_type: 'search', rule_format: 'legado', fetch_mode: 'http', page: 1, show_raw: true }}>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="keyword" label="书名 / 搜索关键词">
              <Input placeholder="例如：斗破苍穹" allowClear />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item
              name="url"
              label="测试 URL"
              rules={[
                {
                  validator: (_, value) => {
                    if (!value || /^https?:\/\//i.test(value)) return Promise.resolve()
                    return Promise.reject(new Error('请输入完整的 http:// 或 https:// 地址'))
                  },
                },
              ]}
            >
              <Input placeholder="目录或正文测试时粘贴目标页面 URL" allowClear />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={5}>
            <Form.Item name="rule_type" label="解析类型">
              <Select
                options={[
                  { label: '搜索结果', value: 'search' },
                  { label: '目录列表', value: 'toc' },
                  { label: '章节正文', value: 'content' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={7}>
            <Form.Item name="fetch_mode" label="请求模式">
              <Segmented
                block
                options={[
                  { label: '普通请求', value: 'http' },
                  { label: '浏览器渲染', value: 'browser' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={4}>
            <Form.Item name="rule_format" label="测试规则格式">
              <Select
                options={[
                  { label: 'Legado', value: 'legado' },
                  { label: 'YLCraft', value: 'ylcraft' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={4}>
            <Form.Item name="page" label="搜索页码">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={4}>
            <Form.Item name="show_raw" label="返回原始 HTML" valuePropName="checked">
              <Switch checkedChildren="开启" unCheckedChildren="关闭" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item
          name="request_headers"
          label="请求头"
          extra="支持 JSON 对象、key: value 多行请求头，或带 GET /path HTTP/1.1 首行的原始请求头。Host、Content-Length、Accept-Encoding 等请求头会被后端忽略。"
        >
          <TextArea rows={8} style={{ fontFamily: 'monospace' }} />
        </Form.Item>
      </Form>
      <Button type="primary" icon={<BugOutlined />} loading={testLoading} onClick={handleRunTest}>
        运行测试
      </Button>
      {renderTestResult()}
    </Space>
  )

  const renderLegadoTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Space wrap>
        <Button icon={<SwapOutlined />} loading={convertLoading === 'ylcraft'} onClick={handleConvertToYlcraft}>
          转换为 YLCraft
        </Button>
        <Button type="primary" icon={<SaveOutlined />} loading={rulesSaving} onClick={handleSaveLegadoRules}>
          保存 Legado 规则
        </Button>
      </Space>
      <Form layout="vertical">
        <Form.Item label="搜索 URL 模板">
          <Input
            value={legadoEditor.searchUrl}
            onChange={event => setLegadoEditor(prev => ({ ...prev, searchUrl: event.target.value }))}
            placeholder="/search?kw={{key}}"
          />
        </Form.Item>
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item label="搜索规则 ruleSearch">
              <TextArea
                value={legadoEditor.ruleSearch}
                onChange={event => setLegadoEditor(prev => ({ ...prev, ruleSearch: event.target.value }))}
                rows={10}
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>
            <Form.Item label="详情规则 ruleBookInfo">
              <TextArea
                value={legadoEditor.ruleBookInfo}
                onChange={event => setLegadoEditor(prev => ({ ...prev, ruleBookInfo: event.target.value }))}
                rows={8}
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="目录规则 ruleToc">
              <TextArea
                value={legadoEditor.ruleToc}
                onChange={event => setLegadoEditor(prev => ({ ...prev, ruleToc: event.target.value }))}
                rows={10}
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>
            <Form.Item label="正文规则 ruleContent">
              <TextArea
                value={legadoEditor.ruleContent}
                onChange={event => setLegadoEditor(prev => ({ ...prev, ruleContent: event.target.value }))}
                rows={8}
                style={{ fontFamily: 'monospace' }}
              />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item label="发现规则 ruleExplore">
          <TextArea
            value={legadoEditor.ruleExplore}
            onChange={event => setLegadoEditor(prev => ({ ...prev, ruleExplore: event.target.value }))}
            rows={5}
            style={{ fontFamily: 'monospace' }}
          />
        </Form.Item>
      </Form>
    </Space>
  )

  const renderYlcraftTab = () => {
    let warnings: string[] = []
    try {
      const parsed = parseJsonObject(ylcraftText, 'YLCraft 规则')
      warnings = Array.isArray(parsed.conversion_warnings) ? parsed.conversion_warnings : []
    } catch {
      warnings = []
    }

    return (
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <Space wrap>
          <Button icon={<SwapOutlined />} loading={convertLoading === 'legado'} onClick={handleConvertToLegado}>
            转换为 Legado
          </Button>
          <Button type="primary" icon={<SaveOutlined />} loading={rulesSaving} onClick={handleSaveYlcraftRules}>
            保存 YLCraft 规则
          </Button>
        </Space>
        {warnings.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={isDark ? darkWarningAlertStyle : undefined}
            message={<span style={isDark ? darkWarningAlertTitleStyle : undefined}>转换提示</span>}
            description={
              <ul style={{ margin: 0, paddingLeft: 18, ...(isDark ? darkWarningAlertDescriptionStyle : {}) }}>
                {warnings.map((item, index) => (
                  <li key={`${item}-${index}`} style={isDark ? darkWarningAlertDescriptionStyle : undefined}>{item}</li>
                ))}
              </ul>
            }
          />
        )}
        <TextArea
          value={ylcraftText}
          onChange={event => setYlcraftText(event.target.value)}
          rows={26}
          style={{ fontFamily: 'monospace' }}
        />
      </Space>
    )
  }

  const renderCookieTab = () => (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      <Alert
        type="info"
        showIcon
        style={isDark ? darkInfoAlertStyle : undefined}
        message={<span style={isDark ? darkInfoAlertTitleStyle : undefined}>Cookie 内容只用于保存或替换</span>}
        description={
          <span style={isDark ? darkInfoAlertDescriptionStyle : undefined}>
            已有 Cookie 不会回显明文内容；需要更新时在表单中重新粘贴 Cookie 内容即可。测试请求会自动按域名匹配启用中的 Cookie。
          </span>
        }
      />
      <Card size="small" title={editingCookie ? '替换 Cookie' : '新增 Cookie'}>
        <Form form={cookieForm} layout="vertical" initialValues={{ is_active: true }}>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="domain" label="域名" rules={[{ required: true, message: '请输入域名' }]}>
                <Input placeholder="m.example.com / .example.com / *" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="description" label="说明">
                <Input placeholder="登录态、VIP、备用线路等" />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item name="expires_at" label="过期时间">
                <Input placeholder="2027-01-01T00:00:00" />
              </Form.Item>
            </Col>
            <Col xs={24} md={2}>
              <Form.Item name="is_active" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="cookie_content" label="Cookie 内容">
            <TextArea rows={5} placeholder="支持 Cookie 请求头或 Netscape cookies.txt 内容" />
          </Form.Item>
          <Space>
            <Button type="primary" icon={editingCookie ? <SaveOutlined /> : <PlusOutlined />} loading={cookieSaving} onClick={handleCookieSubmit}>
              {editingCookie ? '保存替换' : '新增 Cookie'}
            </Button>
            {editingCookie && (
              <Button
                onClick={() => {
                  setEditingCookie(null)
                  cookieForm.resetFields()
                  cookieForm.setFieldsValue({ is_active: true })
                }}
              >
                取消编辑
              </Button>
            )}
            <Button icon={<ReloadOutlined />} onClick={() => debugSource && loadCookies(debugSource.id)}>
              刷新
            </Button>
          </Space>
        </Form>
      </Card>
      <List
        loading={cookiesLoading}
        bordered
        locale={{ emptyText: '暂无 Cookie' }}
        dataSource={cookies}
        renderItem={item => (
          <List.Item
            actions={[
              <Switch
                key="active"
                checked={item.is_active}
                checkedChildren="启用"
                unCheckedChildren="禁用"
                onChange={checked => handleCookieActiveChange(item, checked)}
              />,
              <Button key="edit" type="link" onClick={() => startEditCookie(item)}>
                替换
              </Button>,
              <Popconfirm
                key="delete"
                title="确定删除此 Cookie？"
                onConfirm={() => handleDeleteCookie(item.id)}
                okText="确定"
                cancelText="取消"
              >
                <Button type="link" danger>
                  删除
                </Button>
              </Popconfirm>,
            ]}
          >
            <List.Item.Meta
              avatar={<KeyOutlined />}
              title={
                <Space wrap>
                  <Text code>{item.domain || '*'}</Text>
                  <Tag color={item.is_active ? 'success' : 'default'}>
                    {item.is_active ? '启用' : '禁用'}
                  </Tag>
                  <Tag>{item.cookie_count} 项</Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={2}>
                  <Text type="secondary">{item.description || '无说明'}</Text>
                  <Text type="secondary">过期时间：{item.expires_at || '未设置'}</Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Space>
  )

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>书源管理</Title>
      <Paragraph>
        支持导入 <a href="https://github.com/gedoor/legado" target="_blank" rel="noreferrer">阅读 App（Legado）</a>
        格式和 YLCraft 格式的书源文件，导入后可用于小说搜索、下载和规则调试。
      </Paragraph>

      <Alert
        type="info"
        showIcon
        message={<span style={isDark ? darkInfoAlertTitleStyle : undefined}>书源规则调试</span>}
        description={
          <span style={isDark ? darkInfoAlertDescriptionStyle : undefined}>
            点击书源行内的调试，可以在同一个工作台里测试请求、编辑 Legado 规则、转换 YLCraft 规则，并管理该书源的 Cookie。
          </span>
        }
        style={{ marginBottom: 16, ...(isDark ? darkInfoAlertStyle : {}) }}
      />

      <Divider />

      <Space style={{ marginBottom: 16 }} wrap>
        <Search
          allowClear
          placeholder="搜索书源名称"
          value={sourceNameKeyword}
          onChange={event => {
            setSourceNameKeyword(event.target.value)
            setPagination(prev => ({ ...prev, current: 1 }))
          }}
          onSearch={value => {
            setSourceNameKeyword(value)
            setPagination(prev => ({ ...prev, current: 1 }))
          }}
          style={{ width: 260 }}
        />
        <Upload {...uploadProps}>
          <Button type="primary" icon={<UploadOutlined />}>导入书源 JSON</Button>
        </Upload>
        <Button icon={<DownloadOutlined />} onClick={() => exportBookSources()}>导出书源</Button>
        <Button onClick={fetchSources} loading={loading}>刷新</Button>
        <Button type="primary" onClick={handleBatchEnable} disabled={selectedRowKeys.length === 0}>批量启用</Button>
        <Button danger onClick={handleBatchDisable} disabled={selectedRowKeys.length === 0}>批量禁用</Button>
        <Button type="primary" danger onClick={handleBatchDelete} disabled={selectedRowKeys.length === 0}>批量删除</Button>
      </Space>

      <Card>
        <Table
          dataSource={filteredSources}
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
          scroll={{ x: 1100 }}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
          }}
        />
      </Card>

      <Modal
        open={debugOpen}
        title={debugSource ? `书源调试：${debugSource.book_source_name}` : '书源调试'}
        width={1180}
        onCancel={() => setDebugOpen(false)}
        destroyOnClose={false}
        footer={[
          <Button key="close" onClick={() => setDebugOpen(false)}>
            关闭
          </Button>,
          <Button key="test" type="primary" icon={<BugOutlined />} loading={testLoading} onClick={handleRunTest}>
            运行测试
          </Button>,
        ]}
      >
        {rulesLoading && <Alert type="info" showIcon message="正在加载书源规则" style={{ marginBottom: 12 }} />}
        {rulesMeta && (
          <Descriptions size="small" column={3} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="书源">{rulesMeta.book_source_name}</Descriptions.Item>
            <Descriptions.Item label="格式">{rulesMeta.rule_format}</Descriptions.Item>
            <Descriptions.Item label="版本">{rulesMeta.rule_version || '-'}</Descriptions.Item>
          </Descriptions>
        )}
        <Tabs
          activeKey={activeDebugTab}
          onChange={setActiveDebugTab}
          items={[
            { key: 'test', label: '测试请求', children: renderTestTab() },
            { key: 'legado', label: 'Legado 规则', children: renderLegadoTab() },
            { key: 'ylcraft', label: 'YLCraft 规则', children: renderYlcraftTab() },
            { key: 'cookie', label: 'Cookie', children: renderCookieTab() },
          ]}
        />
      </Modal>
    </div>
  )
}

export default BookSourcePage
