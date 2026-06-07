package com.pdfapps.android.ui.viewmodel

import android.app.Application
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.pdfapps.android.domain.model.ToolId
import com.pdfapps.android.pdf.PdfDocumentSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainViewModel(app: Application) : AndroidViewModel(app) {

    var selectedTool by mutableStateOf(ToolId.Viewer)
        private set

    var openUri by mutableStateOf<Uri?>(null)
        private set

    var pageCount by mutableIntStateOf(0)
        private set

    var currentPage by mutableIntStateOf(0)
        private set

    var currentPageBitmap by mutableStateOf<Bitmap?>(null)
        private set

    private var session: PdfDocumentSession? = null

    fun selectTool(id: ToolId) {
        selectedTool = id
    }

    fun pickAndOpenPdf(uri: Uri) {
        openPdf(uri)
        selectedTool = ToolId.Viewer
    }

    fun openPdf(uri: Uri) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                session?.close()
                val ctx = getApplication<Application>()
                runCatching {
                    ctx.contentResolver.takePersistableUriPermission(
                        uri,
                        android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION,
                    )
                }
                session = PdfDocumentSession.open(ctx, uri)
            }
            openUri = uri
            pageCount = session?.pageCount ?: 0
            currentPage = 0
            renderCurrentPage()
        }
    }

    fun prevPage() {
        if (currentPage > 0) {
            currentPage--
            renderCurrentPage()
        }
    }

    fun nextPage() {
        if (currentPage < pageCount - 1) {
            currentPage++
            renderCurrentPage()
        }
    }

    private fun renderCurrentPage() {
        viewModelScope.launch {
            val bmp = withContext(Dispatchers.IO) {
                session?.renderPage(currentPage, width = 1080)
            }
            currentPageBitmap = bmp
        }
    }

    override fun onCleared() {
        session?.close()
        super.onCleared()
    }
}
