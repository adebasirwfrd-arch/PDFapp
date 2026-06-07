package com.pdfapps.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.pdfapps.android.ui.shell.MainShell
import com.pdfapps.android.ui.theme.PdfAppsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PdfAppsTheme {
                MainShell(
                    initialPdfUri = intent?.data,
                )
            }
        }
    }
}
