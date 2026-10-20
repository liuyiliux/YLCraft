/**
 * 动图切帧的**图源入口**（生成 / 素材库 / 上传，三者平级）。
 *
 * 为什么单独做成一块，而不是挂在切帧面板里：
 * **切图是独立能力，不以"刚生成"为前提。** 常见场景是"多格图早就生成好了，现在想重切一次"，
 * 或者"从素材库挑一张现成的分格图来切"。若把入口藏进切帧面板，
 * 面板就永远处于"没有可用帧"的死状态 —— 用户没有下手处。
 *
 * 三条路径产出同一种东西：一段 `sheetPath`（待切分的图片本地路径/URL）。
 * 后面切帧、合成完全一致。
 */

import { useState } from 'react'
import {
  Alert,
  Button,
  InputNumber,
  Modal,
  Segmented,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import { DatabaseOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import AssetReferencePicker from '../asset-reference-picker/AssetReferencePicker'
import { uploadMotionGifFrame } from '../../api'
import { getAsset } from '../../api'

const { Text } = Typography

interface Props {
  /** 已选的待切分图片（本地路径或 URL）。空串=还没选。 */
  sheetPath: string
  onSheetChange: (path: string, previewUrl?: string) => void
  /** 当前排布（切帧用）。 */
  rows: number
  cols: number
  onShapeChange: (rows: number, cols: number) => void
}

export function MotionSheetSourcePanel({
  sheetPath,
  onSheetChange,
  rows,
  cols,
  onShapeChange,
}: Props) {
  const { theme: THEME } = useTheme()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [shapeOpen, setShapeOpen] = useState(false)
  const [shapeMode, setShapeMode] = useState<'preset' | 'custom'>('preset')
  const [customRows, setCustomRows] = useState(rows)
  const [customCols, setCustomCols] = useState(cols)
  const [uploading, setUploading] = useState(false)

  const hasSheet = Boolean(sheetPath)

  const handleUpload = async (file: File) => {
    // 上传的图必须**落到后端**再把路径交出去：切帧/合成在后端跑，
    // 而 `resolve_asset_file` 对 data: URL 直接返回 None（那是给"前端预览"用的）。
    // 复用上传补位那个端点——两者都是"存一张图拿到序号/路径"，不必再开一个接口。
    setUploading(true)
    try {
      const data = await uploadMotionGifFrame(file)
      if (!data?.success) {
        message.error('上传失败')
        return false
      }
      onSheetChange(data.file_path, URL.createObjectURL(file))
      message.success('已上传，可以直接切帧')
    } catch (e: any) {
      message.error(`上传失败：${e?.message || e}`)
    } finally {
      setUploading(false)
    }
    return false
  }

  const applyShape = () => {
    if (shapeMode === 'preset') {
      setShapeOpen(false)
      return
    }
    const r = Math.max(1, Math.min(8, customRows || 1))
    const c = Math.max(1, Math.min(8, customCols || 1))
    if (r * c > 64) {
      message.error('格数过多（上限 64），请减少行或列')
      return
    }
    onShapeChange(r, c)
    setShapeOpen(false)
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          marginBottom: 10,
        }}
      >
        <Space size={6} wrap>
          <Text strong style={{ fontSize: 13 }}>待切分的图片</Text>
          {hasSheet ? (
            <Tag color="green" style={{ margin: 0 }}>已就绪</Tag>
          ) : (
            <Tag style={{ margin: 0 }}>还没选</Tag>
          )}
        </Space>
        {hasSheet && (
          <Button size="small" onClick={() => onSheetChange('')}>
            换一张
          </Button>
        )}
      </div>

      {/* 两个入口：素材库 / 上传。
          「新生成一批」已移除 —— 生成归生图页，这里只做加工。
          留一个生图入口等于又把两件事混回来，也让这张图在页面上多显示一次。 */}
      <Space wrap>
        <Button
          size="small"
          icon={<DatabaseOutlined />}
          onClick={() => setPickerOpen(true)}
        >
          从素材库选
        </Button>
        <Upload
          accept="image/*"
          showUploadList={false}
          beforeUpload={handleUpload}
          disabled={uploading}
        >
          <Button size="small" icon={<UploadOutlined />} loading={uploading}>
            上传图片
          </Button>
        </Upload>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => {
            setCustomRows(rows)
            setCustomCols(cols)
            setShapeMode('preset')
            setShapeOpen(true)
          }}
        >
          切成 {rows}×{cols}
        </Button>
      </Space>

      {!hasSheet && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 10, fontSize: 12 }}
          message={
            <span style={{ fontSize: 12 }}>
              从素材库挑一张现成的分格图，或上传一张。
              还没有多格图？去
              <a href="/image-gen" style={{ margin: '0 3px' }}>AI 图片</a>
              生成。
            </span>
          }
        />
      )}

      {/* 排布选择：预设 + 自定义行列 */}
      <Modal
        open={shapeOpen}
        title="这张图要切成几格"
        onCancel={() => setShapeOpen(false)}
        onOk={applyShape}
        okText="确定"
        cancelText="取消"
      >
        <Segmented
          value={shapeMode}
          onChange={v => setShapeMode(v as 'preset' | 'custom')}
          options={[
            { label: '常用排布', value: 'preset' },
            { label: '自定义行列', value: 'custom' },
          ]}
          style={{ marginBottom: 14 }}
        />
        {shapeMode === 'preset' ? (
          <Space wrap>
            {[
              { r: 2, c: 4, label: '8 格 2×4（推荐）' },
              { r: 4, c: 4, label: '16 格 4×4' },
              { r: 1, c: 4, label: '4 格 1×4' },
              { r: 3, c: 3, label: '9 格 3×3' },
            ].map(p => (
              <Button
                key={`${p.r}x${p.c}`}
                type={p.r === rows && p.c === cols ? 'primary' : 'default'}
                onClick={() => {
                  onShapeChange(p.r, p.c)
                  setShapeOpen(false)
                }}
              >
                {p.label}
              </Button>
            ))}
          </Space>
        ) : (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div>
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>行数（竖着分几份）</Text>
              <InputNumber
                min={1}
                max={8}
                value={customRows}
                onChange={v => setCustomRows(Number(v) || 1)}
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <div>
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>列数（横着分几份）</Text>
              <InputNumber
                min={1}
                max={8}
                value={customCols}
                onChange={v => setCustomCols(Number(v) || 1)}
                style={{ width: '100%', marginTop: 4 }}
              />
            </div>
            <Alert
              type="info"
              showIcon
              style={{ fontSize: 12 }}
              message={
                <span style={{ fontSize: 12 }}>
                  共 <b>{customRows * customCols}</b> 格。
                  单格像素 = 图宽 ÷ {customCols}、图高 ÷ {customRows}。
                </span>
              }
            />
          </Space>
        )}
      </Modal>

      <AssetReferencePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={async payload => {
          setPickerOpen(false)
          /*
           * ⚠️ **素材库给的是 assetId，不是文件路径**，切帧接口只认路径。
           *
           * `AssetReferencePicker` 有两种模式：
           * - base64 模式：`url` 是空串，**只给 assetId**（那种模式是给生图用的 ——
           *   生图接口自己会解析 assetId）；
           * - 来源 URL 模式：给真实 url。
           *
           * 动图的 `slice-preview` / `compose` **不认识 assetId**（后端解析器只认
           * 文件路径与 `/api/v1/assets/download?path=` 这类地址）。
           * 原来直接把 assetId 当路径传过去 → `多格图不存在或不在允许的目录内：
           * c475e739-…`（用户实测的报错）。
           *
           * 这里先查一次素材详情，拿到 `file_path`（可解析的存储路径）再传。
           * 回退顺序：真实 url → 详情里的 file_path。
           */
          let path = payload.url || ''
          if (!path && payload.assetId) {
            try {
              const res: any = await getAsset(payload.assetId)
              const data = res?.data ?? res
              path = data?.file_path || data?.local_path || data?.url || ''
            } catch (e: any) {
              message.error(`读取素材详情失败：${e?.message || e}`)
              return
            }
          }
          if (!path) {
            message.error('这张素材没有可用的本地文件，无法切帧')
            return
          }
          onSheetChange(path, payload.url || undefined)
          message.success('已载入素材库图片，可直接切帧')
        }}
      />
    </div>
  )
}

export default MotionSheetSourcePanel
