package com.pdfapps.android.pdf

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor

/** Native Android PDF viewing via [PdfRenderer] (read-only). */
class PdfDocumentSession private constructor(
    private val descriptor: ParcelFileDescriptor,
    private val renderer: PdfRenderer,
) {
    val pageCount: Int get() = renderer.pageCount

    fun renderPage(index: Int, width: Int): Bitmap? {
        if (index !in 0 until pageCount) return null
        return renderer.openPage(index).use { page ->
            val scale = width.toFloat() / page.width
            val height = (page.height * scale).toInt().coerceAtLeast(1)
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(Color.WHITE)
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            bitmap
        }
    }

    fun close() {
        renderer.close()
        descriptor.close()
    }

    companion object {
        fun open(context: Context, uri: Uri): PdfDocumentSession {
            val pfd = context.contentResolver.openFileDescriptor(uri, "r")
                ?: error("Cannot open PDF")
            val renderer = PdfRenderer(pfd)
            return PdfDocumentSession(pfd, renderer)
        }
    }
}
