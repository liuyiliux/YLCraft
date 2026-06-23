import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { message } from 'antd'
import { DocumentReader, LocalDocumentPicker } from '../../components/reader'
import { getReaderFile, getReaderFiles, openFolder } from '../../api'
import type { ReaderDocument } from '../../api'

export default function ReaderPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const filePath = searchParams.get('file_path') || searchParams.get('path') || ''
  const filePaths = searchParams.getAll('file_path').filter(Boolean)
  const title = searchParams.get('title') || ''
  const rootPath = searchParams.get('root_path') || ''
  const [doc, setDoc] = useState<ReaderDocument | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)

  const openReaderForFile = (path: string, nextRootPath = rootPath) => {
    setPickerOpen(false)
    const params = new URLSearchParams()
    params.set('file_path', path)
    if (nextRootPath) params.set('root_path', nextRootPath)
    navigate(`/reader?${params.toString()}`)
  }

  const openReaderForFiles = (paths: string[], nextTitle?: string, nextRootPath = rootPath) => {
    const clean = paths.filter(Boolean)
    if (!clean.length) {
      message.warning('没有可阅读文件')
      return
    }
    setPickerOpen(false)
    const params = new URLSearchParams()
    clean.forEach(path => params.append('file_path', path))
    if (nextTitle) params.set('title', nextTitle)
    if (nextRootPath) params.set('root_path', nextRootPath)
    navigate(`/reader?${params.toString()}`)
  }

  const loadDocument = useCallback(async () => {
    if (!filePath && filePaths.length === 0) {
      setError('')
      setDoc(null)
      return
    }

    setLoading(true)
    setError('')
    try {
      const res = filePaths.length > 1
        ? await getReaderFiles(filePaths, title, rootPath)
        : await getReaderFile(filePath || filePaths[0], rootPath)
      setDoc(res)
    } catch (e: any) {
      setDoc(null)
      setError(e?.message || '读取文件失败')
    } finally {
      setLoading(false)
    }
  }, [filePath, filePaths.join('|'), title, rootPath])

  useEffect(() => {
    loadDocument()
  }, [loadDocument])

  return (
    <>
      <DocumentReader
        document={doc}
        loading={loading}
        error={error}
        onBack={() => navigate(-1)}
        onGoCrawler={() => navigate('/crawler')}
        onPickLocal={() => setPickerOpen(true)}
        onReload={loadDocument}
        onOpenFolder={async (path) => {
          try {
            await openFolder(path)
          } catch (e: any) {
            message.error(e?.message || '打开文件夹失败')
          }
        }}
      />
      <LocalDocumentPicker
        open={pickerOpen}
        onCancel={() => setPickerOpen(false)}
        onSelectFile={openReaderForFile}
        onSelectFiles={openReaderForFiles}
      />
    </>
  )
}
