package com.pdfapps.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val PdfAppsDark = darkColorScheme(
    primary = Accent,
    onPrimary = TextPri,
    secondary = AccentHover,
    background = BgBase,
    onBackground = TextPri,
    surface = BgCard,
    onSurface = TextPri,
    surfaceVariant = BgInput,
    onSurfaceVariant = TextSec,
    outline = Border,
)

private val PdfAppsTypography = Typography(
    headlineMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
        color = TextPri,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Bold,
        fontSize = 15.sp,
        color = TextPri,
    ),
    bodyMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 14.sp,
        color = TextPri,
    ),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontSize = 12.sp,
        color = TextSec,
    ),
)

@Composable
fun PdfAppsTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = PdfAppsDark,
        typography = PdfAppsTypography,
        content = content,
    )
}
