package com.pdfapps.android.domain.model

import androidx.annotation.StringRes
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Compress
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.RemoveRedEye
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material.icons.filled.Upload
import androidx.compose.material.icons.filled.GroupWork
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.Approval
import androidx.compose.ui.graphics.vector.ImageVector
import com.pdfapps.android.R

enum class ToolId(val route: String) {
    Split("split"),
    Merge("merge"),
    Reorder("reorder"),
    Extract("extract"),
    Rotate("rotate"),
    Compress("compress"),
    PageNumbers("page_numbers"),
    NUp("nup"),
    Encrypt("encrypt"),
    Watermark("watermark"),
    Ocr("ocr"),
    Convert("convert"),
    Import("import"),
    Edit("edit"),
    Info("info"),
    Viewer("viewer"),
}

data class NavTool(
    val id: ToolId,
    @StringRes val titleRes: Int,
    val icon: ImageVector,
)

data class NavGroup(
    @StringRes val titleRes: Int,
    val tools: List<NavTool>,
)

/** Same order as desktop `_NAV_GROUPS` in app/window.py */
val NavGroups: List<NavGroup> = listOf(
    NavGroup(
        R.string.nav_group_organize,
        listOf(
            NavTool(ToolId.Split, R.string.nav_split, Icons.Default.ContentCut),
            NavTool(ToolId.Merge, R.string.nav_merge, Icons.Default.GroupWork),
            NavTool(ToolId.Reorder, R.string.nav_reorder, Icons.AutoMirrored.Filled.List),
            NavTool(ToolId.Extract, R.string.nav_extract, Icons.Default.FileDownload),
        ),
    ),
    NavGroup(
        R.string.nav_group_transform,
        listOf(
            NavTool(ToolId.Rotate, R.string.nav_rotate, Icons.Default.Refresh),
            NavTool(ToolId.Compress, R.string.nav_compress, Icons.Default.Compress),
            NavTool(ToolId.PageNumbers, R.string.nav_page_numbers, Icons.AutoMirrored.Filled.List),
            NavTool(ToolId.NUp, R.string.nav_nup, Icons.Default.GridView),
        ),
    ),
    NavGroup(
        R.string.nav_group_security,
        listOf(
            NavTool(ToolId.Encrypt, R.string.nav_encrypt, Icons.Default.Lock),
            NavTool(ToolId.Watermark, R.string.nav_watermark, Icons.Default.Approval),
        ),
    ),
    NavGroup(
        R.string.nav_group_convert,
        listOf(
            NavTool(ToolId.Ocr, R.string.nav_ocr, Icons.Default.RemoveRedEye),
            NavTool(ToolId.Convert, R.string.nav_convert, Icons.Default.SwapHoriz),
            NavTool(ToolId.Import, R.string.nav_import, Icons.Default.Upload),
        ),
    ),
    NavGroup(
        R.string.nav_group_annotate,
        listOf(
            NavTool(ToolId.Edit, R.string.nav_edit, Icons.Default.Edit),
        ),
    ),
    NavGroup(
        R.string.nav_group_inspect,
        listOf(
            NavTool(ToolId.Info, R.string.nav_info, Icons.Default.Info),
        ),
    ),
)

val AllTools: List<NavTool> = NavGroups.flatMap { it.tools }
