import { Context } from '@deepseek-ai/cordis'
import { AttachmentId, AttachmentStore } from '@deepseek-ai/dsh-attachment'
import type { ImageAttachmentLimits, ImageAttachmentRef, SaveImageAttachment, StoredImageAttachment } from '@deepseek-ai/dsh-attachment'

/** In-memory attachment store: enough surface to prove the image path end to end. */
export class FakeAttachments extends AttachmentStore {
  readonly saved: SaveImageAttachment[] = []
  readonly imageLimits: ImageAttachmentLimits = {
    maxImageBytes: 5_000_000,
    maxImagesPerMessage: 10,
    maxMessageImageBytes: 20_000_000,
    maxImagePixels: 50_000_000,
    maxImageDimension: 8_000,
    mediaTypes: ['image/png'],
  }

  constructor(ctx: Context) {
    super(ctx)
  }

  async validateImage(): Promise<void> {}

  async saveImage(input: SaveImageAttachment): Promise<ImageAttachmentRef> {
    this.saved.push(input)
    return {
      attachmentId: AttachmentId(`fake-${this.saved.length}`),
      mediaType: input.mediaType,
      bytes: input.data.byteLength,
      width: 1,
      height: 1,
      ...input.name === undefined ? {} : { name: input.name },
    }
  }

  async readImage(ref: ImageAttachmentRef): Promise<StoredImageAttachment> {
    const index = Number(String(ref.attachmentId).replace('fake-', '')) - 1
    const saved = this.saved[index]
    if (saved === undefined) throw new Error('unknown attachment')
    return { ref, data: saved.data }
  }
}
