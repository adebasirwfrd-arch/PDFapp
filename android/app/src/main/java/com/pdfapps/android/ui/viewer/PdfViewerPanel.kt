package com.pdfapps.android.ui.viewer

import android.graphics.Bitmap
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.pdfapps.android.R
import com.pdfapps.android.ui.theme.Accent
import com.pdfapps.android.ui.theme.BgBase
import com.pdfapps.android.ui.theme.BgCard
import com.pdfapps.android.ui.theme.BgInner
import com.pdfapps.android.ui.theme.TextPri
import com.pdfapps.android.ui.theme.TextSec

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PdfViewerPanel(
    openUri: Uri?,
    pageCount: Int,
    currentPage: Int,
    pageBitmap: Bitmap?,
    onOpenPdf: (Uri) -> Unit,
    onPrevPage: () -> Unit,
    onNextPage: () -> Unit,
    onMenuClick: () -> Unit,
) {
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) onOpenPdf(uri)
    }

    Scaffold(
        containerColor = BgBase,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (openUri != null) {
                            openUri.lastPathSegment ?: stringResource(R.string.app_name)
                        } else {
                            stringResource(R.string.viewer_no_document)
                        },
                        color = TextPri,
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onMenuClick) {
                        Icon(Icons.Default.Menu, contentDescription = "Menu", tint = TextPri)
                    }
                },
                actions = {
                    if (pageCount > 0) {
                        Text(
                            "${currentPage + 1} / $pageCount",
                            color = TextSec,
                            modifier = Modifier.padding(end = 8.dp),
                        )
                        IconButton(onClick = onPrevPage, enabled = currentPage > 0) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, null, tint = TextPri)
                        }
                        IconButton(onClick = onNextPage, enabled = currentPage < pageCount - 1) {
                            Icon(Icons.AutoMirrored.Filled.ArrowForward, null, tint = TextPri)
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BgCard),
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(BgInner),
            contentAlignment = Alignment.Center,
        ) {
            when {
                pageBitmap != null -> {
                    Image(
                        bitmap = pageBitmap.asImageBitmap(),
                        contentDescription = "PDF page",
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Fit,
                    )
                }
                openUri == null -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Icon(
                            Icons.Default.PictureAsPdf,
                            contentDescription = null,
                            tint = Accent,
                            modifier = Modifier.padding(8.dp),
                        )
                        Text(
                            stringResource(R.string.viewer_no_document),
                            color = TextSec,
                        )
                        Button(
                            onClick = { picker.launch(arrayOf("application/pdf")) },
                            colors = ButtonDefaults.buttonColors(containerColor = Accent),
                        ) {
                            Text(stringResource(R.string.viewer_open_pdf))
                        }
                    }
                }
                else -> {
                    Text("Loading…", color = TextSec)
                }
            }
        }
    }
}
