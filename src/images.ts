import { readFile } from 'node:fs/promises'
import { basename } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import { AttachmentId } from '@deepseek-ai/dsh-attachment'
import type { ImageAttachmentRef } from '@deepseek-ai/dsh-attachment'
import '@deepseek-ai/dsh-attachment'
import type { JsonObject } from './protocol.ts'

/** Serializable record of a plot persisted through the attachment service. */
export type SavedImage = {
  attachmentId: string
  mediaType: 'image/png'
  bytes: number
  width: number
  height: number
  name: string
  title: string
  path: string
}

export interface SaveImagesOutcome {
  images: SavedImage[]
  /** Human-readable reasons a plot stayed on disk only. */
  skipped: string[]
}

/**
 * Persist worker-produced PNGs through `ctx.attachments` so they can be
 * returned as image content blocks. The service is optional: without it the
 * plots stay on disk and the renderer only mentions their paths.
 */
export async function saveInlineImages(ctx: Context, plots: JsonObject[], enabled: boolean): Promise<SaveImagesOutcome> {
  const outcome: SaveImagesOutcome = { images: [], skipped: [] }
  if (!enabled || plots.length === 0) return outcome
  const store = ctx.get('attachments')
  if (store === undefined) {
    outcome.skipped.push('no attachment service mounted; plots are on disk only')
    return outcome
  }
  for (const plot of plots) {
    const path = typeof plot['path'] === 'string' ? plot['path'] : undefined
    if (path === undefined) continue
    const title = typeof plot['title'] === 'string' ? plot['title'] : basename(path)
    try {
      const data = await readFile(path)
      const ref = await store.saveImage({ data: new Uint8Array(data), mediaType: 'image/png', name: basename(path) })
      outcome.images.push({
        attachmentId: String(ref.attachmentId),
        mediaType: 'image/png',
        bytes: ref.bytes,
        width: ref.width,
        height: ref.height,
        name: ref.name ?? basename(path),
        title,
        path,
      })
    } catch (error) {
      outcome.skipped.push(`${basename(path)}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  return outcome
}

/** Rebuild image content blocks from the canonical value (render must stay pure). */
export function imageBlocks(images: readonly SavedImage[]): { type: 'image'; attachment: ImageAttachmentRef }[] {
  return images.map(image => ({
    type: 'image' as const,
    attachment: {
      attachmentId: AttachmentId(image.attachmentId),
      mediaType: image.mediaType,
      bytes: image.bytes,
      width: image.width,
      height: image.height,
      name: image.name,
    },
  }))
}

export function isSavedImage(value: unknown): value is SavedImage {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v['attachmentId'] === 'string' && typeof v['bytes'] === 'number' && typeof v['width'] === 'number' && typeof v['height'] === 'number'
}
