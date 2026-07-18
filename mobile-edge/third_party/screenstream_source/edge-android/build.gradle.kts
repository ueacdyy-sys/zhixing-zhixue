plugins {
    alias(libs.plugins.androidLibrary)
    alias(libs.plugins.kotlin.parcelize)
    alias(libs.plugins.kotlin.compose)
}

kotlin {
    explicitApi()
    jvmToolchain(17)
}

android {
    namespace = "cn.zhixingzhixue.edge.android"
    compileSdk = rootProject.extra["compileSdkVersion"] as Int
    buildToolsVersion = rootProject.extra["buildToolsVersion"] as String

    defaultConfig {
        minSdk = rootProject.extra["minSdkVersion"] as Int
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    api(projects.learningApplication)
    implementation(projects.common)
    implementation(projects.rtsp)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
}
