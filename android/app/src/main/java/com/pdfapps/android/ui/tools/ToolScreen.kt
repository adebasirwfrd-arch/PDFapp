package com.pdfapps.android.ui.tools

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.pdfapps.android.R
import com.pdfapps.android.domain.model.AllTools
import com.pdfapps.android.domain.model.ToolId
import com.pdfapps.android.ui.theme.Accent
import com.pdfapps.android.ui.theme.BgBase
import com.pdfapps.android.ui.theme.BgCard
import com.pdfapps.android.ui.theme.BgInner
import com.pdfapps.android.ui.theme.TextPri
import com.pdfapps.android.ui.theme.TextSec

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ToolScreen(
    toolId: ToolId,
    openUri: Uri?,
    onMenuClick: () -> Unit,
) {
    val tool = AllTools.first { it.id == toolId }
    val title = stringResource(tool.titleRes)

    Scaffold(
        containerColor = BgBase,
        topBar = {
            TopAppBar(
                title = { Text(title, color = TextPri) },
                navigationIcon = {
                    IconButton(onClick = onMenuClick) {
                        Icon(Icons.Default.Menu, contentDescription = "Menu", tint = TextPri)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BgCard),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(BgInner)
                .padding(20.dp),
        ) {
            ToolHeader(title = title)
            Spacer(Modifier.height(16.dp))
            Text(
                text = stringResource(R.string.tool_coming_soon),
                style = MaterialTheme.typography.bodyMedium,
                color = TextSec,
            )
            if (openUri != null) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Open: ${openUri.lastPathSegment ?: openUri}",
                    style = MaterialTheme.typography.labelMedium,
                    color = TextSec,
                )
            }
            Spacer(Modifier.height(24.dp))
            ImplementationPhase(toolId)
        }
    }
}

@Composable
private fun ToolHeader(title: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(BgCard)
            .padding(20.dp),
    ) {
        Text(title, style = MaterialTheme.typography.headlineMedium, color = TextPri)
        Spacer(Modifier.height(4.dp))
        Text(
            "Desktop parity · ${phaseLabel(title)}",
            style = MaterialTheme.typography.labelMedium,
            color = Accent,
        )
    }
}

@Composable
private fun ImplementationPhase(toolId: ToolId) {
    val phase = when (toolId) {
        ToolId.Split, ToolId.Merge, ToolId.Rotate, ToolId.Extract, ToolId.Info -> "Phase 1 — PDFBox"
        ToolId.Compress, ToolId.Encrypt, ToolId.Watermark -> "Phase 2"
        ToolId.Ocr -> "Phase 3 — ML Kit"
        ToolId.Convert, ToolId.Import -> "Phase 4"
        ToolId.Edit -> "Phase 5 — editor (text snap, area move, multiline)"
        ToolId.Reorder, ToolId.PageNumbers, ToolId.NUp -> "Phase 2"
        ToolId.Viewer -> "Ready"
    }
    Text("Roadmap: $phase", style = MaterialTheme.typography.labelMedium, color = TextSec)
}

private fun phaseLabel(title: String) = title
