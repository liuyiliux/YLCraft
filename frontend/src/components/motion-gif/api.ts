/** 动图（motion GIF）接口封装。 */

import {
  composeMotionGif,
  getMotionGifOptions,
  previewMotionGifPrompt,
  previewMotionGifSlice,
  saveMotionGif,
  uploadMotionGifFrame,
} from '../../api'
import type {
  MotionGifComposeResponse,
  MotionGifOptionsResponse,
  MotionGifSaveResponse,
  MotionPromptPreviewResponse,
  SlicePreviewResponse,
} from './motionGifConfig'

export {
  composeMotionGif,
  getMotionGifOptions,
  previewMotionGifPrompt,
  previewMotionGifSlice,
  saveMotionGif,
  uploadMotionGifFrame,
}

export type {
  MotionGifComposeResponse,
  MotionGifOptionsResponse,
  MotionPromptPreviewResponse,
  SlicePreviewResponse,
}

export type { MotionGifSaveResponse }
