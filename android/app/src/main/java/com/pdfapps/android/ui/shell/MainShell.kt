package com.pdfapps.android.ui.shell

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pdfapps.android.domain.model.ToolId
import com.pdfapps.android.ui.sidebar.SidebarDrawer
import com.pdfapps.android.ui.tools.ToolScreen
import com.pdfapps.android.ui.viewer.PdfViewerPanel
import com.pdfapps.android.ui.theme.BgBase
import com.pdfapps.android.ui.viewmodel.MainViewModel
import kotlinx.coroutines.launch

@Composable
fun MainShell(
    initialPdfUri: Uri?,
    viewModel: MainViewModel = viewModel(),
) {
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    if (initialPdfUri != null && viewModel.openUri == null) {
        viewModel.openPdf(initialPdfUri)
        viewModel.selectTool(ToolId.Viewer)
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            SidebarDrawer(
                selected = viewModel.selectedTool,
                onSelect = { tool ->
                    viewModel.selectTool(tool.id)
                    scope.launch { drawerState.close() }
                },
                onClose = { scope.launch { drawerState.close() } },
            )
        },
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .background(BgBase),
        ) {
            Box(modifier = Modifier.weight(1f)) {
                if (viewModel.selectedTool == ToolId.Viewer) {
                    PdfViewerPanel(
                        openUri = viewModel.openUri,
                        pageCount = viewModel.pageCount,
                        currentPage = viewModel.currentPage,
                        pageBitmap = viewModel.currentPageBitmap,
                        onOpenPdf = viewModel::pickAndOpenPdf,
                        onPrevPage = viewModel::prevPage,
                        onNextPage = viewModel::nextPage,
                        onMenuClick = { scope.launch { drawerState.open() } },
                    )
                } else {
                    ToolScreen(
                        toolId = viewModel.selectedTool,
                        openUri = viewModel.openUri,
                        onMenuClick = { scope.launch { drawerState.open() } },
                    )
                }
            }
        }
    }
}
