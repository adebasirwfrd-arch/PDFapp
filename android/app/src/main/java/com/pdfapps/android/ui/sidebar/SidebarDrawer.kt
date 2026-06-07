package com.pdfapps.android.ui.sidebar

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.pdfapps.android.R
import com.pdfapps.android.domain.model.AllTools
import com.pdfapps.android.domain.model.NavGroup
import com.pdfapps.android.domain.model.NavGroups
import com.pdfapps.android.domain.model.NavTool
import com.pdfapps.android.domain.model.ToolId
import com.pdfapps.android.ui.theme.Accent
import com.pdfapps.android.ui.theme.BgSide
import com.pdfapps.android.ui.theme.Border
import com.pdfapps.android.ui.theme.NavSelectedBg
import com.pdfapps.android.ui.theme.NavSelectedBorder
import com.pdfapps.android.ui.theme.NavSelectedText
import com.pdfapps.android.ui.theme.TextPri
import com.pdfapps.android.ui.theme.TextSec

@Composable
fun SidebarDrawer(
    selected: ToolId,
    onSelect: (NavTool) -> Unit,
    onClose: () -> Unit,
) {
    ModalDrawerSheet(
        modifier = Modifier.width(300.dp),
        drawerContainerColor = BgSide,
    ) {
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .verticalScroll(rememberScrollState())
                .padding(vertical = 12.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    Icons.Default.PictureAsPdf,
                    contentDescription = null,
                    tint = Accent,
                    modifier = Modifier.size(28.dp),
                )
                Spacer(Modifier.width(10.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        stringResource(R.string.app_name),
                        style = MaterialTheme.typography.titleMedium,
                        color = TextPri,
                    )
                    Text(
                        stringResource(R.string.app_subtitle),
                        style = MaterialTheme.typography.labelMedium,
                        color = TextSec,
                    )
                }
                IconButton(onClick = onClose) {
                    Icon(Icons.Default.Close, contentDescription = "Close", tint = TextPri)
                }
            }

            HorizontalDivider(color = Border, modifier = Modifier.padding(horizontal = 12.dp))

            NavGroups.forEach { group ->
                NavGroupSection(
                    group = group,
                    selected = selected,
                    onSelect = onSelect,
                )
            }

            Spacer(Modifier.height(16.dp))
            Text(
                text = "v1.13.15 · Android native port",
                style = MaterialTheme.typography.labelMedium,
                color = TextSec,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

@Composable
private fun NavGroupSection(
    group: NavGroup,
    selected: ToolId,
    onSelect: (NavTool) -> Unit,
) {
    Text(
        text = stringResource(group.titleRes).uppercase(),
        style = MaterialTheme.typography.labelMedium,
        color = TextSec,
        modifier = Modifier.padding(start = 20.dp, top = 16.dp, bottom = 6.dp),
    )
    group.tools.forEach { tool ->
        NavItem(
            tool = tool,
            selected = tool.id == selected,
            onClick = { onSelect(tool) },
        )
    }
}

@Composable
private fun NavItem(
    tool: NavTool,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(6.dp)
    val bg = if (selected) NavSelectedBg else BgSide
    val borderColor = if (selected) NavSelectedBorder else Border.copy(alpha = 0f)
    val textColor = if (selected) NavSelectedText else TextSec

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 2.dp)
            .clip(shape)
            .background(bg)
            .border(1.dp, borderColor, shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(tool.icon, contentDescription = null, tint = if (selected) Accent else TextSec)
        Spacer(Modifier.width(12.dp))
        Text(
            stringResource(tool.titleRes),
            color = textColor,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

/** All tools flat — used by search later */
@Suppress("unused")
val flatTools: List<NavTool> = AllTools
